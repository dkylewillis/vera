export function AskSetupDialog({
  onUseVeraPro,
  onAddOwnProvider,
  onClose,
}: {
  onUseVeraPro: () => void;
  onAddOwnProvider: () => void;
  onClose: () => void;
}) {
  return (
    <div className="modalBackdrop" onClick={onClose}>
      <div className="modal askSetupDialog" role="dialog" aria-modal="true" aria-labelledby="ask-setup-title" onClick={(event) => event.stopPropagation()}>
        <header className="modalHeader">
          <h2 id="ask-setup-title">Ask needs a model</h2>
        </header>
        <div className="settingsForm">
          <p className="providerItemDescription">
            Search works without an account. Ask needs either a VERA Pro subscription or a provider you configure yourself.
          </p>
          <div className="editorActions askSetupActions">
            <button type="button" className="primaryAction" onClick={onUseVeraPro}>Use VERA Pro</button>
            <button type="button" className="secondaryAction" onClick={onAddOwnProvider}>Add your own provider</button>
          </div>
        </div>
      </div>
    </div>
  );
}
