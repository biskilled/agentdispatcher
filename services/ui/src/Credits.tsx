import { useState } from "react";

type Notice = {
  name: string;
  version: string;
  license: string;
  source: string;
  texts: { file: string; text: string }[];
};

/** Load shipped notices on demand; one artifact supplies both attribution and license texts. */
export function Credits() {
  const [notices, setNotices] = useState<Notice[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  async function show() {
    setOpen(true);
    try {
      const response = await fetch("/notices.json");
      if (!response.ok)
        throw new Error(
          "Could not load dependency notices. See THIRD_PARTY_NOTICES.md in the source repository.",
        );
      setNotices(await response.json());
    } catch (failure) {
      setError((failure as Error).message);
    }
  }
  return (
    <>
      <button className="credits-button" onClick={show}>
        Open-source licenses
      </button>
      {open && (
        <dialog
          open
          className="credits-dialog"
          aria-label="Open-source licenses"
        >
          <div className="section-heading">
            <h2>Built with open source</h2>
            <button className="secondary" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>
          <div className="credits-body">
            <p>
              AgentDispatcher is Apache 2.0. Dependencies retain their own
              licenses and copyrights.
            </p>
            {error && <p role="alert">{error}</p>}
            {notices.map((item) => (
              <details key={item.name}>
                <summary>
                  {item.name} {item.version}
                </summary>
                <p>{item.license}</p>
                <a href={item.source} target="_blank" rel="noreferrer">
                  Project source
                </a>
                {item.texts.map((file) => (
                  <pre key={file.file}>{file.text}</pre>
                ))}
              </details>
            ))}
          </div>
        </dialog>
      )}
    </>
  );
}
