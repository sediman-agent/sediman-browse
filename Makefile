.PHONY: build-tui build-release clean-tui test-tui

# Build the Rust TUI (debug)
build-tui:
	cargo build -p sediman-tui

# Build the Rust TUI (release)
build-release:
	cargo build --release -p sediman-tui

# Run tests
test-tui:
	cargo test --workspace -- --test-threads=1

# Clean Rust artifacts
clean-tui:
	cargo clean

# Build and install the TUI binary to ~/.cargo/bin
install-tui: build-release
	cp target/release/sediman-tui ~/.cargo/bin/
	@echo "Installed to ~/.cargo/bin/sediman-tui"
