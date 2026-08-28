package cli

import (
	"fmt"
	"io"

	"waywarden/internal/distribution/contracts"
)

func WriteHumanVersion(stdout io.Writer, name, version string) {
	_, _ = fmt.Fprintf(stdout, "%s %s\n", name, version)
}

func WriteCommandResultJSON(stdout io.Writer, result contracts.CommandResult) error {
	data, err := contracts.CanonicalBytes(result)
	if err != nil {
		return err
	}
	if err := contracts.ValidateSchema(contracts.SchemaCommandResult, data); err != nil {
		return err
	}
	_, err = stdout.Write(data)
	return err
}

func WritePublicErrorJSON(stdout io.Writer, publicErr contracts.PublicError) error {
	data, err := contracts.CanonicalBytes(publicErr)
	if err != nil {
		return err
	}
	if err := contracts.ValidateSchema(contracts.SchemaError, data); err != nil {
		return err
	}
	_, err = stdout.Write(data)
	return err
}
