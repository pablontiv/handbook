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
	"waywarden/internal/distribution/planning"
)

var planAdapterFactory = func() filesystem.Adapter {
	return filesystem.NewLocalAdapter()
}

func newPlanCommand(stdout io.Writer, stderr io.Writer, outputFormat *string) *cobra.Command {
	var inventoryPath string
	var intent string
	var installationID string
	var backupSetID string
	var receiptID string
	var out string
	var stateRoot string
	cmd := &cobra.Command{
		Use:   "plan",
		Short: "Build a deterministic Waywarden distribution plan from an inventory artifact",
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := validateOutputFormat(*outputFormat); err != nil {
				return err
			}
			if inventoryPath == "" || intent == "" || out == "" {
				writeHumanPlanSummary(stderr, "plan failed")
				return exitError{code: contracts.ExitInvalidInput}
			}
			if *outputFormat == contracts.OutputJSON && out == "-" {
				writeHumanPlanSummary(stderr, "plan failed")
				return exitError{code: contracts.ExitInvalidInput}
			}
			if out != "-" && !filepath.IsAbs(out) {
				writeHumanPlanSummary(stderr, "plan failed")
				return exitError{code: contracts.ExitInvalidInput}
			}
			if stateRoot != "" && !filepath.IsAbs(stateRoot) {
				writeHumanPlanSummary(stderr, "plan failed")
				return exitError{code: contracts.ExitInvalidInput}
			}

			selector := selectorFromFlags(installationID, backupSetID, receiptID)
			options := planning.Options{Intent: contracts.PlanIntent(intent), Selector: selector, InventoryPath: contracts.AbsolutePath(inventoryPath), ArtifactLabel: artifactLabel(out)}
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

			result, err := planning.NewService(planAdapterFactory()).Plan(cmd.Context(), options)
			writeHumanPlanSummary(stderr, planSummary(result, err))
			if out != "-" && *outputFormat == contracts.OutputJSON && result.Schema != "" {
				status := contracts.ResultStatusSuccess
				var commandErr *contracts.NestedPublicError
				if err != nil {
					status = contracts.ResultStatusBlocked
					commandErr = nestedPlanningError(err)
				}
				if writeErr := cli.WriteCommandResultJSON(stdout, contracts.CommandResult{Schema: contracts.SchemaCommandResult, Kind: contracts.ResultArtifact, Command: "plan", Status: status, Artifact: &result, Error: commandErr}); writeErr != nil && err == nil {
					return exitError{code: contracts.ExitStateOrIOFailure}
				}
			}
			if err != nil {
				var planErr planning.Error
				if errors.As(err, &planErr) {
					return exitError{code: planErr.Exit}
				}
				return err
			}
			return nil
		},
	}
	cmd.Flags().StringVar(&inventoryPath, "inventory", "", "canonical inventory artifact path")
	cmd.Flags().StringVar(&intent, "intent", "", "plan intent (install|uninstall|restore)")
	cmd.Flags().StringVar(&installationID, "installation", "", "installation selector")
	cmd.Flags().StringVar(&backupSetID, "backup", "", "backup set selector")
	cmd.Flags().StringVar(&receiptID, "receipt", "", "receipt selector")
	cmd.Flags().StringVar(&out, "out", "-", "artifact output path or - for stdout")
	cmd.Flags().StringVar(&stateRoot, "state-root", "", "absolute Waywarden state root")
	return cmd
}

func selectorFromFlags(installationID, backupSetID, receiptID string) *contracts.Selector {
	count := 0
	if installationID != "" {
		count++
	}
	if backupSetID != "" {
		count++
	}
	if receiptID != "" {
		count++
	}
	if count == 0 {
		return nil
	}
	selector := &contracts.Selector{}
	if installationID != "" {
		selector.Kind = contracts.SelectorInstallation
		selector.InstallationID = installationID
	}
	if backupSetID != "" {
		selector.Kind = contracts.SelectorBackupSet
		selector.BackupSetID = backupSetID
	}
	if receiptID != "" {
		selector.Kind = contracts.SelectorReceipt
		selector.ReceiptID = receiptID
	}
	return selector
}

func planSummary(result contracts.ArtifactResult, err error) string {
	if result.Schema == "" {
		if err != nil {
			return "plan failed"
		}
		return "plan completed"
	}
	if err != nil {
		return "plan completed with blockers"
	}
	return "plan completed"
}

func writeHumanPlanSummary(stderr io.Writer, summary string) {
	_, _ = fmt.Fprintf(stderr, "%s\n", summary)
}

func nestedPlanningError(err error) *contracts.NestedPublicError {
	var planErr planning.Error
	if errors.As(err, &planErr) {
		return &contracts.NestedPublicError{Code: planErr.Code, Message: planErr.Message, Exit: planErr.Exit, Evidence: []contracts.EvidenceRef{}}
	}
	return &contracts.NestedPublicError{Code: "plan_failed", Message: "plan failed", Exit: contracts.ExitStateOrIOFailure, Evidence: []contracts.EvidenceRef{}}
}
