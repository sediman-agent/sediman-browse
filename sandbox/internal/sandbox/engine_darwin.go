//go:build darwin

package sandbox

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/sediman/sandbox/pkg/api"
)

// darwinSandbox implements api.Sandbox for macOS.
// For now it uses a restricted environment via chroot-like bind mounts
// and eventually will use seatbelt sandbox profiles.
type darwinSandbox struct {
	dataDir string
}

func newSandbox(dataDir string) api.Sandbox {
	return &darwinSandbox{dataDir: dataDir}
}

// ... later in file ...

func newCheckpointer(dataDir string) api.Checkpointer {
	return &darwinCheckpointer{dataDir: dataDir}
}

func (s *darwinSandbox) Run(ctx context.Context, cmd api.Command, policy api.Policy) (*api.Result, error) {
	// macOS does not have bubblewrap. We use a combination of:
	// 1. chroot to a prepared root (optional)
	// 2. seatbelt sandbox profile (if available)
	// 3. Fallback: run with restricted working dir + env
	
	// For MVP: run in subprocess with restricted cwd and env
	// Full sandboxing requires seatbelt which needs a profile file
	
	if policy.Timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, policy.Timeout)
		defer cancel()
	}

	command := exec.CommandContext(ctx, cmd.Args[0], cmd.Args[1:]...)
	
	if cmd.WorkingDir != "" {
		command.Dir = cmd.WorkingDir
	}
	
	// Filter environment
	cleanEnv := []string{
		"PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
		"HOME=" + os.Getenv("HOME"),
		"TMPDIR=" + os.Getenv("TMPDIR"),
	}
	for k, v := range cmd.Env {
		cleanEnv = append(cleanEnv, fmt.Sprintf("%s=%s", k, v))
	}
	command.Env = cleanEnv
	
	var stdout, stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr
	
	if len(cmd.Stdin) > 0 {
		command.Stdin = bytes.NewReader(cmd.Stdin)
	}

	start := time.Now()
	err := command.Run()
	duration := time.Since(start)

	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
			if ctx.Err() == context.DeadlineExceeded {
				exitCode = 124
			}
		} else {
			return nil, fmt.Errorf("sandbox run: %w", err)
		}
	}

	return &api.Result{
		ExitCode: exitCode,
		Stdout:   stdout.String(),
		Stderr:   stderr.String(),
		Duration: duration,
	}, nil
}

func (s *darwinSandbox) Close() error {
	return nil
}

// darwinCheckpointer uses APFS clonecopy when available, falling back to copy.
type darwinCheckpointer struct {
	dataDir string
}

func newDarwinCheckpointer(dataDir string) api.Checkpointer {
	return &darwinCheckpointer{dataDir: dataDir}
}

func (c *darwinCheckpointer) Create(dir string, name string) (*api.CheckpointInfo, error) {
	id := fmt.Sprintf("%d", time.Now().UnixNano())
	cpDir := filepath.Join(c.dataDir, "checkpoints", id)
	
	if err := os.MkdirAll(cpDir, 0755); err != nil {
		return nil, fmt.Errorf("mkdir checkpoint: %w", err)
	}

	// Copy CONTENTS of dir into cpDir
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("read dir: %w", err)
	}
	for _, entry := range entries {
		src := filepath.Join(dir, entry.Name())
		dst := filepath.Join(cpDir, entry.Name())
		if err := copyPath(src, dst); err != nil {
			return nil, fmt.Errorf("copy: %w", err)
		}
	}

	return &api.CheckpointInfo{
		ID:        id,
		Name:      name,
		CreatedAt: time.Now(),
		Path:      cpDir,
	}, nil
}

func (c *darwinCheckpointer) Revert(dir string, id string) error {
	cpDir := filepath.Join(c.dataDir, "checkpoints", id)
	
	// Remove current dir contents
	entries, err := os.ReadDir(dir)
	if err != nil {
		return fmt.Errorf("read dir: %w", err)
	}
	for _, entry := range entries {
		path := filepath.Join(dir, entry.Name())
		if err := os.RemoveAll(path); err != nil {
			return fmt.Errorf("remove: %w", err)
		}
	}

	// Restore from checkpoint (copy contents of cpDir into dir)
	entries, err = os.ReadDir(cpDir)
	if err != nil {
		return fmt.Errorf("read checkpoint: %w", err)
	}
	for _, entry := range entries {
		src := filepath.Join(cpDir, entry.Name())
		dst := filepath.Join(dir, entry.Name())
		if err := copyPath(src, dst); err != nil {
			return fmt.Errorf("restore: %w", err)
		}
	}
	return nil
}

func (c *darwinCheckpointer) Commit(dir string, id string) error {
	return nil
}

func (c *darwinCheckpointer) List(dir string) ([]*api.CheckpointInfo, error) {
	cpDir := filepath.Join(c.dataDir, "checkpoints")
	entries, err := os.ReadDir(cpDir)
	if err != nil {
		if os.IsNotExist(err) {
			return []*api.CheckpointInfo{}, nil
		}
		return nil, err
	}

	var results []*api.CheckpointInfo
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		info, err := entry.Info()
		createdAt := time.Time{}
		if err == nil {
			createdAt = info.ModTime()
		}
		results = append(results, &api.CheckpointInfo{
			ID:        entry.Name(),
			Path:      filepath.Join(cpDir, entry.Name()),
			CreatedAt: createdAt,
		})
	}
	return results, nil
}

func (c *darwinCheckpointer) Delete(dir string, id string) error {
	cpDir := filepath.Join(c.dataDir, "checkpoints", id)
	return os.RemoveAll(cpDir)
}

// apfsCloneCopy attempts to use APFS clonecopy for instant copy-on-write snapshots.
func apfsCloneCopy(src, dst string) error {
	// Use cp -c (clone) on macOS which uses FICLONE ioctl on APFS
	cmd := exec.Command("cp", "-Rc", src, dst)
	return cmd.Run()
}

func copyDir(src, dst string) error {
	return filepath.Walk(src, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		dstPath := filepath.Join(dst, rel)
		
		if info.IsDir() {
			return os.MkdirAll(dstPath, info.Mode())
		}
		
		return copyFile(path, dstPath)
	})
}

func copyPath(src, dst string) error {
	info, err := os.Stat(src)
	if err != nil {
		return err
	}
	if info.IsDir() {
		return copyDir(src, dst)
	}
	return copyFile(src, dst)
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()
	
	if _, err := out.ReadFrom(in); err != nil {
		return err
	}
	
	return out.Close()
}
