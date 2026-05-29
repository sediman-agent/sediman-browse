use std::num::NonZeroU64;
use std::sync::Arc;

use wgpu::util::{DeviceExt, BufferInitDescriptor};
use wgpu::*;

use crate::renderer::CellBuffer;
use crate::renderer::diff::DiffEngine;

use super::atlas::FontAtlas;

const SHADER: &str = r#"
struct VertexInput {
    @location(0) pos: vec2<f32>,
    @location(1) uv: vec2<f32>,
    @location(2) fg: vec4<f32>,
    @location(3) bg: vec4<f32>,
    @location(4) flags: f32,
}

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) fg: vec4<f32>,
    @location(2) bg: vec4<f32>,
    @location(3) flags: f32,
}

struct Uniforms {
    screen_w: f32,
    screen_h: f32,
    cell_w: f32,
    cell_h: f32,
}

@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var t: texture_2d<f32>;
@group(0) @binding(2) var s: sampler;

@vertex
fn vs(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    out.position = vec4f(
        (in.pos.x / u.screen_w) * 2.0 - 1.0,
        1.0 - (in.pos.y / u.screen_h) * 2.0,
        0.0, 1.0
    );
    out.uv = in.uv;
    out.fg = in.fg;
    out.bg = in.bg;
    out.flags = in.flags;
    return out;
}

@fragment
fn fs(in: VertexOutput) -> @location(0) vec4f {
    let is_bg = in.flags < 0.5;
    if is_bg {
        return in.bg;
    }
    let a = textureSample(t, s, in.uv).r;
    let fg = in.fg * a;
    let bg = in.bg * (1.0 - a);
    return vec4f(fg.rgb + bg.rgb, 1.0);
}
"#;

#[repr(C)]
#[derive(Copy, Clone, Debug, bytemuck::Pod, bytemuck::Zeroable)]
struct GpuVertex {
    pos: [f32; 2],
    uv: [f32; 2],
    fg: [f32; 4],
    bg: [f32; 4],
    flags: f32,
}

impl GpuVertex {
    const LAYOUT: VertexBufferLayout<'static> = VertexBufferLayout {
        array_stride: std::mem::size_of::<GpuVertex>() as u64,
        step_mode: VertexStepMode::Vertex,
        attributes: &[
            VertexAttribute { offset: 0, format: VertexFormat::Float32x2, shader_location: 0 },
            VertexAttribute { offset: 8, format: VertexFormat::Float32x2, shader_location: 1 },
            VertexAttribute { offset: 16, format: VertexFormat::Float32x4, shader_location: 2 },
            VertexAttribute { offset: 32, format: VertexFormat::Float32x4, shader_location: 3 },
            VertexAttribute { offset: 48, format: VertexFormat::Float32, shader_location: 4 },
        ],
    };
}

#[repr(C)]
#[derive(Copy, Clone, Debug, bytemuck::Pod, bytemuck::Zeroable)]
struct Uniforms {
    screen_w: f32,
    screen_h: f32,
    cell_w: f32,
    cell_h: f32,
}

const MAX_VERTICES: u64 = 512 * 1024;
const MAX_INDICES: u64 = 768 * 1024;

pub struct GpuRenderer {
    surface: Surface<'static>,
    device: Device,
    queue: Queue,
    config: SurfaceConfiguration,
    pipeline: RenderPipeline,
    atlas: FontAtlas,
    #[allow(dead_code)]
    glyph_texture: Texture,
    glyph_bind_group: BindGroup,
    uniform_buffer: Buffer,
    prev_buffer: CellBuffer,
    vertex_buf: Buffer,
    index_buf: Buffer,
    bg_color: [f32; 4],
}

impl GpuRenderer {
    pub async fn new(window: Arc<winit::window::Window>, font_data: &[u8], font_size: f32) -> Self {
        let size = window.inner_size();
        let w = size.width.max(1);
        let h = size.height.max(1);

        let instance = Instance::new(&InstanceDescriptor::default());
        let surface = instance.create_surface(Arc::clone(&window))
            .expect("Failed to create GPU surface — no compatible display available");

        let adapter = instance
            .request_adapter(&RequestAdapterOptions {
                power_preference: PowerPreference::HighPerformance,
                compatible_surface: Some(&surface),
                force_fallback_adapter: false,
            })
            .await
            .expect("Failed to get GPU adapter — no compatible GPU found");

        let (device, queue) = adapter
            .request_device(
                &DeviceDescriptor {
                    label: Some("sediman-gpu"),
                    required_features: Features::empty(),
                    required_limits: Limits::default(),
                    memory_hints: MemoryHints::Performance,
                },
                None,
            )
            .await
            .expect("Failed to get GPU device — driver issue or insufficient resources");

        let caps = surface.get_capabilities(&adapter);
        let format = caps
            .formats
            .iter()
            .find(|f| f.is_srgb())
            .copied()
            .unwrap_or(caps.formats[0]);

        let config = SurfaceConfiguration {
            usage: TextureUsages::RENDER_ATTACHMENT,
            format,
            width: w,
            height: h,
            present_mode: PresentMode::AutoNoVsync,
            desired_maximum_frame_latency: 1,
            alpha_mode: caps.alpha_modes[0],
            view_formats: vec![],
        };
        surface.configure(&device, &config);

        let atlas = FontAtlas::new(font_data, font_size);
        let atlas_size = Extent3d {
            width: atlas.width,
            height: atlas.height,
            depth_or_array_layers: 1,
        };
        let glyph_texture = device.create_texture(&TextureDescriptor {
            label: Some("glyph-atlas"),
            size: atlas_size,
            mip_level_count: 1,
            sample_count: 1,
            dimension: TextureDimension::D2,
            format: TextureFormat::Rgba8Unorm,
            usage: TextureUsages::TEXTURE_BINDING | TextureUsages::COPY_DST,
            view_formats: &[],
        });
        queue.write_texture(
            TexelCopyTextureInfo {
                texture: &glyph_texture,
                mip_level: 0,
                origin: Origin3d::ZERO,
                aspect: TextureAspect::All,
            },
            &atlas.pixels,
            TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(atlas.width * 4),
                rows_per_image: Some(atlas.height),
            },
            atlas_size,
        );

        let glyph_view = glyph_texture.create_view(&TextureViewDescriptor::default());
        let glyph_sampler = device.create_sampler(&SamplerDescriptor {
            address_mode_u: AddressMode::ClampToEdge,
            address_mode_v: AddressMode::ClampToEdge,
            address_mode_w: AddressMode::ClampToEdge,
            mag_filter: FilterMode::Linear,
            min_filter: FilterMode::Linear,
            ..Default::default()
        });

        let uniforms = Uniforms { screen_w: w as f32, screen_h: h as f32, cell_w: 0.0, cell_h: 0.0 };
        let uniform_buffer = device.create_buffer_init(&BufferInitDescriptor {
            label: Some("uniforms"),
            contents: bytemuck::cast_slice(&[uniforms]),
            usage: BufferUsages::UNIFORM | BufferUsages::COPY_DST,
        });

        let bind_group_layout = device.create_bind_group_layout(&BindGroupLayoutDescriptor {
            label: Some("bg-layout"),
            entries: &[
                BindGroupLayoutEntry {
                    binding: 0,
                    visibility: ShaderStages::VERTEX | ShaderStages::FRAGMENT,
                    ty: BindingType::Buffer {
                        ty: BufferBindingType::Uniform,
                        has_dynamic_offset: false,
                        min_binding_size: NonZeroU64::new(std::mem::size_of::<Uniforms>() as u64),
                    },
                    count: None,
                },
                BindGroupLayoutEntry {
                    binding: 1,
                    visibility: ShaderStages::FRAGMENT,
                    ty: BindingType::Texture {
                        sample_type: TextureSampleType::Float { filterable: true },
                        view_dimension: TextureViewDimension::D2,
                        multisampled: false,
                    },
                    count: None,
                },
                BindGroupLayoutEntry {
                    binding: 2,
                    visibility: ShaderStages::FRAGMENT,
                    ty: BindingType::Sampler(SamplerBindingType::Filtering),
                    count: None,
                },
            ],
        });

        let glyph_bind_group = device.create_bind_group(&BindGroupDescriptor {
            label: Some("glyph-bg"),
            layout: &bind_group_layout,
            entries: &[
                BindGroupEntry { binding: 0, resource: uniform_buffer.as_entire_binding() },
                BindGroupEntry { binding: 1, resource: BindingResource::TextureView(&glyph_view) },
                BindGroupEntry { binding: 2, resource: BindingResource::Sampler(&glyph_sampler) },
            ],
        });

        let pipeline_layout = device.create_pipeline_layout(&PipelineLayoutDescriptor {
            label: Some("pipeline-layout"),
            bind_group_layouts: &[&bind_group_layout],
            push_constant_ranges: &[],
        });

        let shader = device.create_shader_module(ShaderModuleDescriptor {
            label: Some("shader"),
            source: ShaderSource::Wgsl(SHADER.into()),
        });

        let pipeline = device.create_render_pipeline(&RenderPipelineDescriptor {
            label: Some("pipeline"),
            layout: Some(&pipeline_layout),
            vertex: VertexState {
                module: &shader,
                entry_point: Some("vs"),
                buffers: &[GpuVertex::LAYOUT],
                compilation_options: Default::default(),
            },
            fragment: Some(FragmentState {
                module: &shader,
                entry_point: Some("fs"),
                targets: &[Some(ColorTargetState {
                    format: config.format,
                    blend: Some(BlendState::ALPHA_BLENDING),
                    write_mask: ColorWrites::ALL,
                })],
                compilation_options: Default::default(),
            }),
            primitive: PrimitiveState {
                topology: PrimitiveTopology::TriangleList,
                ..Default::default()
            },
            depth_stencil: None,
            multisample: MultisampleState::default(),
            multiview: None,
            cache: None,
        });

        let vertex_buf = device.create_buffer(&BufferDescriptor {
            label: Some("vertex-pool"),
            size: MAX_VERTICES * std::mem::size_of::<GpuVertex>() as u64,
            usage: BufferUsages::VERTEX | BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let index_buf = device.create_buffer(&BufferDescriptor {
            label: Some("index-pool"),
            size: MAX_INDICES * 4,
            usage: BufferUsages::INDEX | BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        Self {
            surface,
            device,
            queue,
            config,
            pipeline,
            atlas,
            glyph_texture,
            glyph_bind_group,
            uniform_buffer,
            prev_buffer: CellBuffer::empty(),
            vertex_buf,
            index_buf,
            bg_color: [0.10, 0.11, 0.15, 1.0],
        }
    }

    pub fn resize(&mut self, width: u32, height: u32) {
        if width > 0 && height > 0 {
            self.config.width = width;
            self.config.height = height;
            self.surface.configure(&self.device, &self.config);
        }
    }

    pub fn set_bg_color(&mut self, r: f32, g: f32, b: f32) {
        self.bg_color = [r, g, b, 1.0];
    }

    pub fn render(&mut self, buffer: &CellBuffer, cell_w: f32, cell_h: f32) -> Result<(), SurfaceError> {
        let uniforms = Uniforms {
            screen_w: self.config.width as f32,
            screen_h: self.config.height as f32,
            cell_w,
            cell_h,
        };
        self.queue.write_buffer(&self.uniform_buffer, 0, bytemuck::cast_slice(&[uniforms]));

        let changes = if self.prev_buffer.width() == buffer.width()
            && self.prev_buffer.height() == buffer.height()
        {
            DiffEngine::diff(&self.prev_buffer, buffer)
        } else {
            self.prev_buffer = CellBuffer::new(buffer.width(), buffer.height());
            DiffEngine::diff(&self.prev_buffer, buffer)
        };

        let default_fg: [f32; 4] = [0.78, 0.82, 0.91, 1.0];
        let default_bg: [f32; 4] = self.bg_color;

        let mut vertices: Vec<GpuVertex> = Vec::with_capacity(changes.len() * 8);
        let mut indices: Vec<u32> = Vec::with_capacity(changes.len() * 12);

        for change in &changes {
            let col = change.x as f32;
            let row = change.y as f32;
            let x0 = col * cell_w;
            let y0 = row * cell_h;
            let x1 = x0 + cell_w;
            let y1 = y0 + cell_h;

            let fg = change.cell.style.fg.map_or(default_fg, |c| {
                let (r, g, b) = c.to_rgb();
                [r as f32 / 255.0, g as f32 / 255.0, b as f32 / 255.0, 1.0]
            });
            let bg = change.cell.style.bg.map_or(default_bg, |c| {
                let (r, g, b) = c.to_rgb();
                [r as f32 / 255.0, g as f32 / 255.0, b as f32 / 255.0, 1.0]
            });

            {
                let base = vertices.len() as u32;
                vertices.extend_from_slice(&[
                    GpuVertex { pos: [x0, y0], uv: [0.0, 0.0], fg, bg, flags: 0.0 },
                    GpuVertex { pos: [x1, y0], uv: [1.0, 0.0], fg, bg, flags: 0.0 },
                    GpuVertex { pos: [x1, y1], uv: [1.0, 1.0], fg, bg, flags: 0.0 },
                    GpuVertex { pos: [x0, y1], uv: [0.0, 1.0], fg, bg, flags: 0.0 },
                ]);
                indices.extend_from_slice(&[base, base + 1, base + 2, base, base + 2, base + 3]);
            }

            if change.cell.ch != ' ' && change.cell.ch != '\0' {
                let glyph = self.atlas.get_or_default(change.cell.ch);
                if let Some((rx, ry, rw, rh)) = self.atlas.take_dirty_rect() {
                    let row_bytes = self.atlas.width as usize * 4;
                    let sub_data: Vec<u8> = (ry..rh).flat_map(|row| {
                        let start = (row as usize * row_bytes) + (rx as usize * 4);
                        self.atlas.pixels[start..start + (rw - rx) as usize * 4].iter().copied()
                    }).collect();
                    self.queue.write_texture(
                        TexelCopyTextureInfo {
                            texture: &self.glyph_texture,
                            mip_level: 0,
                            origin: Origin3d { x: rx, y: ry, z: 0 },
                            aspect: TextureAspect::All,
                        },
                        &sub_data,
                        TexelCopyBufferLayout {
                            offset: 0,
                            bytes_per_row: Some((rw - rx) * 4),
                            rows_per_image: Some(rh - ry),
                        },
                        Extent3d {
                            width: rw - rx,
                            height: rh - ry,
                            depth_or_array_layers: 1,
                        },
                    );
                }
                let base = vertices.len() as u32;
                vertices.extend_from_slice(&[
                    GpuVertex { pos: [x0, y0], uv: [glyph.u0, glyph.v0], fg, bg, flags: 1.0 },
                    GpuVertex { pos: [x1, y0], uv: [glyph.u1, glyph.v0], fg, bg, flags: 1.0 },
                    GpuVertex { pos: [x1, y1], uv: [glyph.u1, glyph.v1], fg, bg, flags: 1.0 },
                    GpuVertex { pos: [x0, y1], uv: [glyph.u0, glyph.v1], fg, bg, flags: 1.0 },
                ]);
                indices.extend_from_slice(&[base, base + 1, base + 2, base, base + 2, base + 3]);
            }
        }

        self.prev_buffer = buffer.clone();

        let vert_bytes = bytemuck::cast_slice(&vertices);
        let idx_bytes = bytemuck::cast_slice(&indices);

        if !vertices.is_empty() {
            let vert_count = vertices.len() as u64;
            let idx_count = indices.len() as u64;
            if vert_count > MAX_VERTICES || idx_count > MAX_INDICES {
                return Ok(());
            }
            self.queue.write_buffer(&self.vertex_buf, 0, vert_bytes);
            self.queue.write_buffer(&self.index_buf, 0, idx_bytes);
        }

        let output = self.surface.get_current_texture()?;
        let view = output.texture.create_view(&TextureViewDescriptor::default());

        let mut encoder = self.device.create_command_encoder(&CommandEncoderDescriptor { label: None });
        {
            let mut pass = encoder.begin_render_pass(&RenderPassDescriptor {
                label: None,
                color_attachments: &[Some(RenderPassColorAttachment {
                    view: &view,
                    resolve_target: None,
                    ops: Operations {
                        load: LoadOp::Clear(Color {
                            r: self.bg_color[0] as f64,
                            g: self.bg_color[1] as f64,
                            b: self.bg_color[2] as f64,
                            a: 1.0,
                        }),
                        store: StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });

            if !indices.is_empty() {
                pass.set_pipeline(&self.pipeline);
                pass.set_bind_group(0, &self.glyph_bind_group, &[]);
                pass.set_vertex_buffer(0, self.vertex_buf.slice(..));
                pass.set_index_buffer(self.index_buf.slice(..), IndexFormat::Uint32);
                pass.draw_indexed(0..indices.len() as u32, 0, 0..1);
            }
        }

        self.queue.submit([encoder.finish()]);
        output.present();

        Ok(())
    }

    pub fn full_redraw(&mut self, buffer: &CellBuffer, cell_w: f32, cell_h: f32) -> Result<(), SurfaceError> {
        self.prev_buffer = CellBuffer::empty();
        self.render(buffer, cell_w, cell_h)
    }
}
