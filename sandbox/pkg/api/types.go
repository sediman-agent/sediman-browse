// Package api defines the public types and interfaces for sediman-sandbox.
package api

import (
	"context"
	"time"
)

// Sandbox defines the interface for running commands in an isolated environment.
type Sandbox interface {
	// Run executes a command in the sandbox with the given policy.
	Run(ctx context.Context, cmd Command, policy Policy) (*Result, error)
	
	// Close cleans up any resources held by the sandbox.
	Close() error
}

// Command is the request to run a command in the sandbox.
type Command struct {
	Args       []string          // e.g. ["bash", "-c", "npm test"]
	WorkingDir string            // Working directory inside the sandbox
	Env        map[string]string // Additional environment variables
	Stdin      []byte            // Optional stdin
}

// Policy controls what the sandboxed process is allowed to do.
type Policy struct {
	AllowDirs     []string          // Writable directories (default: working dir)
	AllowNet      bool              // Allow network access
	AllowNetHosts []string          // If AllowNet, restrict to these hosts
	MaxCPUPct     int               // Max CPU % (0 = no limit)
	MaxMemoryMB   int               // Max memory in MB (0 = no limit)
	Timeout       time.Duration     // Max execution time
}

// Result is the output of a sandboxed command.
type Result struct {
	ExitCode   int
	Stdout     string
	Stderr     string
	Duration   time.Duration
	Checkpoint *CheckpointInfo     // If a checkpoint was created during run
}

// CheckpointInfo describes a filesystem checkpoint.
type CheckpointInfo struct {
	ID        string
	Name      string
	CreatedAt time.Time
	Path      string            // Path to the checkpoint directory
}

// Checkpointer manages filesystem checkpoints.
type Checkpointer interface {
	// Create captures the current state of a directory as a checkpoint.
	Create(dir string, name string) (*CheckpointInfo, error)
	
	// Revert restores a directory to the state captured in the checkpoint.
	Revert(dir string, id string) error
	
	// Commit merges checkpoint changes back into the base directory.
	Commit(dir string, id string) error
	
	// List returns all checkpoints for a directory.
	List(dir string) ([]*CheckpointInfo, error)
	
	// Delete removes a checkpoint.
	Delete(dir string, id string) error
}

// PlatformConfig holds platform-specific settings.
type PlatformConfig struct {
	OS           string
	SandboxBin   string            // bwrap on Linux, seatbelt on macOS
	OverlayType  string            // overlayfs, apfs_clone, reflink_copy
	DataDir      string
}
