package cli

import (
	"fmt"
	"io"
)

func WriteHumanVersion(stdout io.Writer, name, version string) {
	_, _ = fmt.Fprintf(stdout, "%s %s\n", name, version)
}
