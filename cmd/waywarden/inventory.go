package main

import (
	"errors"
	"fmt"
	"io"
	"path/filepath"

	"github.com/spf13/cobra"

	"waywarden/internal/distribution/cli"
	"waywarden/internal/distribution/contracts"
	"waywarden/internal/distribution/filesystem"
	"waywarden/internal/distribution/inventory"
)

type exitError struct {
	code int
}

func (e exitError) Error() string { return fmt.Sprintf("exit %d", e.code) }

func newInventoryCommand(stdout io.Writer, stderr io.Writer, outputFormat *string) *cobra.Command {
	var out string
	var manifestPath string
	var stateRoot string
	cmd := &cobra.Command{
		Use:   "inventory",
		Short: "Write a read-only Waywarden inventory artifact",
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := validateOutputFormat(*outputFormat); err != nil {
				return err
			}
			if *outputFormat == contracts.OutputJSON && out == "-" {
				return exitError{code: contracts.ExitInvalidInput}
			}
			adapter := filesystem.NewLocalAdapter()
			if out != "-" {
				if !filepath.IsAbs(out) {
					return exitError{code: contracts.ExitInvalidInput}
				}
				obs, err := adapter.ObserveNoFollow(cmd.Context(), contracts.AbsolutePath(out))
				if err != nil {
					return exitError{code: contracts.ExitStateOrIOFailure}
				}
				if obs.Exists {
					writeHumanInventorySummary(stderr, "artifact destination already exists")
					return exitError{code: contracts.ExitPreconditionFailed}
				}
			}

			options := inventory.Options{ManifestPath: manifestPath, ArtifactLabel: artifactLabel(out)}
			if stateRoot != "" {
				options.StateRoot = contracts.AbsolutePath(stateRoot)
			}
			if out == "-" {
				options.ArtifactSink = func(data []byte) error {
					_, err := stdout.Write(data)
					return err
				}
			} else {
				options.Destination = contracts.AbsolutePath(out)
			}
			result, err := inventory.NewService(adapter).Inventory(cmd.Context(), options)
			writeHumanInventorySummary(stderr, inventorySummary(result, err))
			if out != "-" && *outputFormat == contracts.OutputJSON && result.Schema != "" {
				status := contracts.ResultStatusSuccess
				if err != nil {
					status = contracts.ResultStatusBlocked
				}
				if writeErr := cli.WriteCommandResultJSON(stdout, contracts.CommandResult{Schema: contracts.SchemaCommandResult, Kind: contracts.ResultArtifact, Command: "inventory", Status: status, Artifact: &result}); writeErr != nil && err == nil {
					return exitError{code: contracts.ExitStateOrIOFailure}
				}
			}
			if err != nil {
				var invErr inventory.Error
				if errors.As(err, &invErr) {
					return exitError{code: invErr.Exit}
				}
				return err
			}
			return nil
		},
	}
	cmd.Flags().StringVar(&out, "out", "-", "artifact output path or - for stdout")
	cmd.Flags().StringVar(&manifestPath, "manifest", "", "absolute manifest override")
	cmd.Flags().StringVar(&stateRoot, "state-root", "", "absolute Waywarden state root")
	return cmd
}

func artifactLabel(out string) string {
	if out == "-" {
		return "stdout"
	}
	return "artifact file"
}

func inventorySummary(result contracts.ArtifactResult, err error) string {
	if result.Schema == "" {
		if err != nil {
			return "inventory failed"
		}
		return "inventory completed"
	}
	if err != nil {
		return "inventory completed with blockers"
	}
	return "inventory completed"
}

func writeHumanInventorySummary(stderr io.Writer, summary string) {
	_, _ = fmt.Fprintf(stderr, "%s\n", summary)
}
