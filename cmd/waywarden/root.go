package main

import (
	"fmt"
	"io"

	"github.com/spf13/cobra"

	"waywarden/internal/distribution/cli"
)

const version = "0.0.0-dev"

func Execute(args []string, stdout io.Writer, stderr io.Writer) int {
	cmd := newRootCommand(stdout, stderr)
	cmd.SetArgs(args)
	if err := cmd.Execute(); err != nil {
		return cli.ExitUsage
	}
	return cli.ExitOK
}

func newRootCommand(stdout io.Writer, stderr io.Writer) *cobra.Command {
	var outputFormat string
	cmd := &cobra.Command{
		Use:           "waywarden",
		Short:         "Waywarden",
		SilenceErrors: true,
		SilenceUsage:  true,
		Version:       version,
		RunE: func(cmd *cobra.Command, args []string) error {
			return cmd.Help()
		},
	}
	cmd.SetHelpCommand(nil)
	cmd.CompletionOptions.DisableDefaultCmd = true
	cmd.SetOut(stdout)
	cmd.SetErr(stderr)
	cmd.SetVersionTemplate("waywarden {{.Version}}\n")
	cmd.PersistentFlags().StringVar(&outputFormat, "output", "human", "output format")
	cmd.AddCommand(newStubCommand("inventory"), newStubCommand("plan"), newStubCommand("apply"), newStubCommand("verify"), newStubCommand("uninstall"), newStubCommand("restore"))
	_ = outputFormat
	return cmd
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
