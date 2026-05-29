//go:build linux

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

// linuxSandbox implements api.Sandbox for Linux using bubblewrap.
type linuxSandbox struct {
	dataDir string
}

func newSandbox(dataDir string) api.Sandbox {
	return &linuxSandbox{dataDir: dataDir}
}

// ... later in file ...

func newCheckpointer(dataDir string) api.Checkpointer {
	return &linuxCheckpointer{dataDir: dataDir}
}

func (s *linuxSandbox) Run(ctx context.Context, cmd api.Command, policy api.Policy) (*api.Result, error) {
	bwrapPath, err := exec.LookPath("bwrap")
	if err != nil {
		return nil, fmt.Errorf("bubblewrap (bwrap) not found: %w", err)
	}

	// Build bwrap args
	args := []string{
		bwrapPath,
		"--die-with-parent",
		"--unshare-all",
		"--proc", "/proc",
		"--dev", "/dev",
		"--tmpfs", "/tmp",
		"--ro-bind", "/usr", "/usr",
		"--ro-bind", "/lib", "/lib",
		"--ro-bind", "/lib64", "/lib64",
		"--ro-bind", "/bin", "/bin",
		"--ro-bind", "/sbin", "/sbin",
		"--ro-bind", "/etc", "/etc",
	}

	// Bind allowed dirs
	for _, dir := range policy.AllowDirs {
		abs, _ := filepath.Abs(dir)
		args = append(args, "--bind", abs, abs)
	}

	// Working dir
	if cmd.WorkingDir != "" {
		args = append(args, "--chdir", cmd.WorkingDir)
	}

	// Set env
	for k, v := range cmd.Env {
		args = append(args, "--setenv", k, v)
	}

	// Append the command to run
	args = append(args, cmd.Args...)

	// Timeout context
	if policy.Timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, policy.Timeout)
		defer cancel()
	}

	command := exec.CommandContext(ctx, args[0], args[1:]...)
	
	var stdout, stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr
	
	if len(cmd.Stdin) > 0 {
		command.Stdin = bytes.NewReader(cmd.Stdin)
	}

	start := time.Now()
	err = command.Run()
	duration := time.Since(start)

	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
			if ctx.Err() == context.DeadlineExceeded {
				exitCode = 124 // standard timeout exit code
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

func (s *linuxSandbox) Close() error {
	return nil
}

// linuxCheckpointer implements copy-based checkpoints.
type linuxCheckpointer struct {
	dataDir string
}

func newLinuxCheckpointer(dataDir string) api.Checkpointer {
	return &linuxCheckpointer{dataDir: dataDir}
}

func (c *linuxCheckpointer) Create(dir string, name string) (*api.CheckpointInfo, error) {
	id := fmt.Sprintf("%d", time.Now().UnixNano())
	cpDir := filepath.Join(c.dataDir, "checkpoints", id)
	
	if err := os.MkdirAll(cpDir, 0755); err != nil {
		return nil, fmt.Errorf("mkdir checkpoint: %w", err)
	}

	if err := copyDir(dir, cpDir); err != nil {
		return nil, fmt.Errorf("copy dir: %w", err)
	}

	return &api.CheckpointInfo{
		ID:        id,
		Name:      name,
		CreatedAt: time.Now(),
		Path:      cpDir,
	}, nil
}

func (c *linuxCheckpointer) Revert(dir string, id string) error {
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

	// Restore from checkpoint
	return copyDir(cpDir, dir)
}

func (c *linuxCheckpointer) Commit(dir string, id string) error {
	return nil
}

func (c *linuxCheckpointer) List(dir string) ([]*api.CheckpointInfo, error) {
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
		results = append(results, &api.CheckpointInfo{
			ID:   entry.Name(),
			Path: filepath.Join(cpDir, entry.Name()),
		})
	}
	return results, nil
}

func (c *linuxCheckpointer) Delete(dir string, id string) error {
	cpDir := filepath.Join(c.dataDir, "checkpoints", id)
	return os.RemoveAll(cpDir)
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
