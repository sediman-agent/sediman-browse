package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"github.com/sediman/sandbox/internal/sandbox"
	"github.com/sediman/sandbox/pkg/api"
)

var (
	engine     *sandbox.Engine
	dataDir    string
)

func main() {
	var rootCmd = &cobra.Command{
		Use:   "sediman-sandbox",
		Short: "Filesystem sandbox + checkpointing for Sediman agent",
		Long: `sediman-sandbox runs commands in isolated filesystem environments
with automatic checkpointing and revert capabilities.

Examples:
  # Run a command with restricted filesystem access
  sediman-sandbox run --allow-dir=/workspace -- bash -c "make test"

  # Create a checkpoint before a risky operation
  sediman-sandbox checkpoint create /workspace --name="before-refactor"

  # Revert if things go wrong
  sediman-sandbox checkpoint revert /workspace --id=<checkpoint-id>
`,
		PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
			var err error
			engine, err = sandbox.NewEngine(dataDir)
			return err
		},
		PersistentPostRunE: func(cmd *cobra.Command, args []string) error {
			if engine != nil {
				return engine.Close()
			}
			return nil
		},
	}

	rootCmd.PersistentFlags().StringVar(&dataDir, "data-dir", "",
		"Directory for sandbox data (default: ~/.sediman/sandbox)")

	// run command
	var allowDirs []string
	var allowNet bool
	var timeoutStr string
	var workDir string

	runCmd := &cobra.Command{
		Use:   "run [flags] -- <command> [args...]",
		Short: "Run a command in a sandboxed environment",
		Example: `  sediman-sandbox run --allow-dir=/workspace --allow-net --timeout=30s -- bash -c "npm test"
  sediman-sandbox run --allow-dir=/tmp --allow-dir=/home/user/project -- python script.py`,
		RunE: func(cmd *cobra.Command, args []string) error {
			if len(args) == 0 {
				return fmt.Errorf("no command specified")
			}

			timeout, err := time.ParseDuration(timeoutStr)
			if err != nil {
				return fmt.Errorf("invalid timeout: %w", err)
			}

			policy := api.Policy{
				AllowDirs: allowDirs,
				AllowNet:  allowNet,
				Timeout:   timeout,
			}

			command := api.Command{
				Args:       args,
				WorkingDir: workDir,
			}

			ctx := context.Background()
			result, err := engine.Run(ctx, command, policy)
			if err != nil {
				return fmt.Errorf("run failed: %w", err)
			}

			fmt.Fprintln(os.Stdout, result.Stdout)
			fmt.Fprintln(os.Stderr, result.Stderr)
			
			if result.ExitCode != 0 {
				return fmt.Errorf("exit code %d", result.ExitCode)
			}
			return nil
		},
	}

	runCmd.Flags().StringArrayVar(&allowDirs, "allow-dir", []string{},
		"Directory to allow read/write access (can be specified multiple times)")
	runCmd.Flags().BoolVar(&allowNet, "allow-net", false,
		"Allow network access")
	runCmd.Flags().StringVar(&timeoutStr, "timeout", "300s",
		"Maximum execution time (e.g. 30s, 5m)")
	runCmd.Flags().StringVar(&workDir, "work-dir", "",
		"Working directory for the command")

	// checkpoint commands
	checkpointCmd := &cobra.Command{
		Use:   "checkpoint",
		Short: "Manage filesystem checkpoints",
	}

	var checkpointName string
	createCmd := &cobra.Command{
		Use:   "create <dir>",
		Short: "Create a checkpoint of a directory",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			dir := args[0]
			info, err := engine.CreateCheckpoint(dir, checkpointName)
			if err != nil {
				return err
			}
			fmt.Printf("Created checkpoint %s (%s)\n", info.ID, info.Name)
			fmt.Printf("  Path: %s\n", info.Path)
			return nil
		},
	}
	createCmd.Flags().StringVar(&checkpointName, "name", "",
		"Name for the checkpoint (optional)")

	var checkpointID string
	revertCmd := &cobra.Command{
		Use:   "revert <dir>",
		Short: "Revert a directory to a checkpoint",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if checkpointID == "" {
				return fmt.Errorf("--id is required")
			}
			dir := args[0]
			if err := engine.RevertCheckpoint(dir, checkpointID); err != nil {
				return err
			}
			fmt.Printf("Reverted %s to checkpoint %s\n", dir, checkpointID)
			return nil
		},
	}
	revertCmd.Flags().StringVar(&checkpointID, "id", "",
		"Checkpoint ID to revert to")
	revertCmd.MarkFlagRequired("id")

	commitCmd := &cobra.Command{
		Use:   "commit <dir>",
		Short: "Commit checkpoint changes back to the base directory",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if checkpointID == "" {
				return fmt.Errorf("--id is required")
			}
			dir := args[0]
			if err := engine.CommitCheckpoint(dir, checkpointID); err != nil {
				return err
			}
			fmt.Printf("Committed checkpoint %s to %s\n", checkpointID, dir)
			return nil
		},
	}
	commitCmd.Flags().StringVar(&checkpointID, "id", "",
		"Checkpoint ID to commit")
	commitCmd.MarkFlagRequired("id")

	listCmd := &cobra.Command{
		Use:   "list [dir]",
		Short: "List checkpoints for a directory (or all if no dir)",
		Args:  cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			dir := ""
			if len(args) > 0 {
				dir = args[0]
			}
			checkpoints, err := engine.ListCheckpoints(dir)
			if err != nil {
				return err
			}
			if len(checkpoints) == 0 {
				fmt.Println("No checkpoints found")
				return nil
			}
			if dir != "" {
				fmt.Printf("Checkpoints for %s:\n", dir)
			} else {
				fmt.Println("All checkpoints:")
			}
			for _, cp := range checkpoints {
				name := cp.Name
				if name == "" {
					name = "(unnamed)"
				}
				fmt.Printf("  %s  %s  %s\n", cp.ID, name, cp.CreatedAt.Format(time.RFC3339))
			}
			return nil
		},
	}

	deleteCmd := &cobra.Command{
		Use:   "delete <dir>",
		Short: "Delete a checkpoint",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if checkpointID == "" {
				return fmt.Errorf("--id is required")
			}
			dir := args[0]
			if err := engine.DeleteCheckpoint(dir, checkpointID); err != nil {
				return err
			}
			fmt.Printf("Deleted checkpoint %s\n", checkpointID)
			return nil
		},
	}
	deleteCmd.Flags().StringVar(
		&checkpointID, "id", "",
		"Checkpoint ID to delete")
	deleteCmd.MarkFlagRequired("id")

	checkpointCmd.AddCommand(createCmd, revertCmd, commitCmd, listCmd, deleteCmd)
	rootCmd.AddCommand(runCmd, checkpointCmd)

	if err := rootCmd.Execute(); err != nil {
		if strings.Contains(err.Error(), "exit code") {
			os.Exit(1)
		}
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
