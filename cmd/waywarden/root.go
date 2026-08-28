package main

import (
	"errors"
	"fmt"
	"io"

	"github.com/spf13/cobra"

	"waywarden/internal/distribution/cli"
	"waywarden/internal/distribution/contracts"
)

const version = "0.0.0-dev"

func Execute(args []string, stdout io.Writer, stderr io.Writer) int {
	cmd := newRootCommand(stdout, stderr)
	cmd.SetArgs(args)
	if err := cmd.Execute(); err != nil {
		var exitErr exitError
		if errors.As(err, &exitErr) {
			return exitErr.code
		}
		return cli.ExitUsage
	}
	return cli.ExitOK
}

func newRootCommand(stdout io.Writer, stderr io.Writer) *cobra.Command {
	var outputFormat string
	var versionFlag bool
	cmd := &cobra.Command{
		Use:           "waywarden",
		Short:         "Waywarden",
		SilenceErrors: true,
		SilenceUsage:  true,
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := validateOutputFormat(outputFormat); err != nil {
				return err
			}
			if versionFlag {
				return writeVersion(stdout, outputFormat)
			}
			return cmd.Help()
		},
	}
	cmd.SetHelpCommand(nil)
	cmd.CompletionOptions.DisableDefaultCmd = true
	cmd.SetOut(stdout)
	cmd.SetErr(stderr)
	cmd.PersistentFlags().StringVar(&outputFormat, "output", contracts.OutputHuman, "output format (human|json)")
	cmd.PersistentFlags().BoolVar(&versionFlag, "version", false, "print version")
	cmd.AddCommand(newInventoryCommand(stdout, stderr, &outputFormat), newPlanCommand(stdout, stderr, &outputFormat), newStubCommand("apply"), newStubCommand("verify"), newStubCommand("uninstall"), newStubCommand("restore"))
	return cmd
}

func validateOutputFormat(outputFormat string) error {
	if outputFormat != contracts.OutputHuman && outputFormat != contracts.OutputJSON {
		return fmt.Errorf("invalid --output %q: must be human or json", outputFormat)
	}
	return nil
}

func writeVersion(stdout io.Writer, outputFormat string) error {
	if outputFormat == contracts.OutputHuman {
		cli.WriteHumanVersion(stdout, "waywarden", version)
		return nil
	}
	label := "waywarden " + version
	return cli.WriteCommandResultJSON(stdout, contracts.CommandResult{
		Schema:  contracts.SchemaCommandResult,
		Kind:    contracts.ResultArtifact,
		Command: "version",
		Status:  contracts.ResultStatusSuccess,
		Artifact: &contracts.ArtifactResult{
			Schema: contracts.SchemaCommandResult,
			SHA256: contracts.SHA256([]byte(label)),
			Bytes:  fmt.Sprintf("%d", len(label)),
			Label:  label,
		},
	})
}

func newStubCommand(name string) *cobra.Command {
	return &cobra.Command{
		Use:   name,
		Short: fmt.Sprintf("%s is not implemented yet", name),
		RunE: func(cmd *cobra.Command, args []string) error {
			return fmt.Errorf("%s command is not implemented yet", name)
		},
	}
}
