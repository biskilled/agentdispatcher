import { useEffect, useState } from "react";
import { type GatewayConnection } from "./gatewayConnection";

/** Select exact gateway routes, with providers as filters rather than wildcard permissions. */
export function GatewayModelPicker({
  connection,
  value,
  onChange,
  refresh,
}: {
  connection: GatewayConnection | null;
  value: string[];
  onChange: (models: string[]) => void;
  refresh: () => void;
}) {
  const [providers, setProviders] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const catalog = connection?.catalog || [];
  const availableProviders = [
    ...new Set(catalog.map((row) => row.provider)),
  ].sort();
  const choices = [
    ...new Set(
      catalog
        .filter((row) => providers.includes(row.provider))
        .map((row) => row.id),
    ),
  ];
  useEffect(() => {
    if (!connection) return;
    const valid = value.filter((id) => connection.models.includes(id));
    if (valid.length !== value.length) onChange(valid);
  }, [connection, value, onChange]);
  function toggleProvider(provider: string) {
    const next = providers.includes(provider)
      ? providers.filter((item) => item !== provider)
      : [...providers, provider];
    setProviders(next);
    onChange(
      value.filter((id) =>
        catalog.some((row) => row.id === id && next.includes(row.provider)),
      ),
    );
  }
  return (
    <fieldset className="model-picker">
      <legend>Allowed providers and models</legend>
      <div className="model-picker-controls">
        <details>
          <summary>
            Providers ·{" "}
            {
              providers.filter((item) => availableProviders.includes(item))
                .length
            }{" "}
            selected
          </summary>
          <div className="picker-options">
            {availableProviders.map((provider) => (
              <label key={provider} className="picker-option">
                <input
                  type="checkbox"
                  checked={providers.includes(provider)}
                  onChange={() => toggleProvider(provider)}
                />
                <span>{provider}</span>
              </label>
            ))}
            {!availableProviders.length && (
              <p>
                {connection
                  ? "No configured providers yet."
                  : "Loading providers…"}
              </p>
            )}
          </div>
        </details>
        <details>
          <summary>Models · {value.length} selected</summary>
          <label>
            Find a model
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              type="search"
            />
          </label>
          <div className="picker-options">
            {choices
              .filter((id) =>
                catalog.some(
                  (row) =>
                    row.id === id &&
                    `${row.id} ${row.model}`
                      .toLowerCase()
                      .includes(search.toLowerCase()),
                ),
              )
              .map((id) => (
                <label key={id} className="picker-option">
                  <input
                    name="models"
                    value={id}
                    type="checkbox"
                    checked={value.includes(id)}
                    onChange={() =>
                      onChange(
                        value.includes(id)
                          ? value.filter((item) => item !== id)
                          : [...value, id],
                      )
                    }
                  />
                  <span>
                    <strong>{id}</strong>
                    <small>
                      {catalog
                        .filter((row) => row.id === id)
                        .map((row) => `${row.provider} / ${row.model}`)
                        .join(", ")}
                    </small>
                  </span>
                </label>
              ))}
            {!choices.length && (
              <p>Select a provider to choose its configured models.</p>
            )}
          </div>
        </details>
      </div>
      <p>
        {value.length
          ? `Allowed routes: ${value.join(", ")}`
          : "Select at least one model route."}
      </p>
      {connection?.catalog_warning && (
        <p role="status">{connection.catalog_warning}</p>
      )}
      <button type="button" className="secondary" onClick={refresh}>
        Refresh providers &amp; models
      </button>
      <p className="muted">
        Refresh reads LiteLLM again. New models must be enabled on the gateway
        first. Only selected routes are allowed; refreshing never grants new
        permissions automatically.
      </p>
    </fieldset>
  );
}
