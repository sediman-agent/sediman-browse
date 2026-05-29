//go:build !linux && !darwin

package sandbox

import (
	"fmt"
	"runtime"

	"github.com/sediman/sandbox/pkg/api"
)

func newSandbox(dataDir string) api.Sandbox {
	panic(fmt.Sprintf("sandbox not available on %s", runtime.GOOS))
}

func newCheckpointer(dataDir string) api.Checkpointer {
	panic(fmt.Sprintf("checkpointer not available on %s", runtime.GOOS))
}
