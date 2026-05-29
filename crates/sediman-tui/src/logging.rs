use tracing_subscriber::filter::EnvFilter;

pub fn setup() {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info,sediman_tui=debug")),
        )
        .with_target(true)
        .compact()
        .init();
}
