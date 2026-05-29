// Package sandbox provides the unified sandbox engine.
package sandbox

import (
	"context"
	"fmt"
	"os"
	"runtime"

	"github.com/sediman/sandbox/pkg/api"
)

// Engine is the unified sandbox engine that delegates to platform-specific implementations.
type Engine struct {
	impl       api.Sandbox
	checkpointer api.Checkpointer
	dataDir    string
}

// NewEngine creates a new sandbox engine for the current platform.
func NewEngine(dataDir string) (*Engine, error) {
	if dataDir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, fmt.Errorf("home dir: %w", err)
		}
		dataDir = home + "/.sediman/sandbox"
	}
	
	if err := os.MkdirAll(dataDir, 0755); err != nil {
		return nil, fmt.Errorf("mkdir: %w", err)
	}
	
	var impl api.Sandbox
	var checkpointer api.Checkpointer
	
	switch runtime.GOOS {
	case "linux":
		impl = newSandbox(dataDir)
		checkpointer = newCheckpointer(dataDir)
	case "darwin":
		impl = newSandbox(dataDir)
		checkpointer = newCheckpointer(dataDir)
	default:
		return nil, fmt.Errorf("unsupported OS: %s", runtime.GOOS)
	}
	
	return &Engine{
		impl:         impl,
		checkpointer: checkpointer,
		dataDir:      dataDir,
	}, nil
}

// Run executes a command in the sandbox.
func (e *Engine) Run(ctx context.Context, cmd api.Command, policy api.Policy) (*api.Result, error) {
	return e.impl.Run(ctx, cmd, policy)
}

// Checkpoint operations delegate to the checkpointer.
func (e *Engine) CreateCheckpoint(dir string, name string) (*api.CheckpointInfo, error) {
	return e.checkpointer.Create(dir, name)
}

func (e *Engine) RevertCheckpoint(dir string, id string) error {
	return e.checkpointer.Revert(dir, id)
}

func (e *Engine) CommitCheckpoint(dir string, id string) error {
	return e.checkpointer.Commit(dir, id)
}

func (e *Engine) ListCheckpoints(dir string) ([]*api.CheckpointInfo, error) {
	return e.checkpointer.List(dir)
}

func (e *Engine) DeleteCheckpoint(dir string, id string) error {
	return e.checkpointer.Delete(dir, id)
}

// Close cleans up the sandbox engine.
func (e *Engine) Close() error {
	return e.impl.Close()
}
