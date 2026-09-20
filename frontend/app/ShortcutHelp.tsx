"use client";

import { shortcutGroups } from "../lib/keyboard";
import { Modal } from "./Modal";

/**
 * The `?` reference (`docs/UX.md`, "Keyboard map").
 *
 * Rendered from `lib/keyboard.ts`'s `shortcutGroups`, which is the same array
 * the views bind against, so this screen cannot advertise a key that does
 * nothing.
 */
export function ShortcutHelp({ onClose }: { onClose: () => void }) {
  return (
    <Modal
      label="Keyboard shortcuts"
      title="Keyboard shortcuts"
      onClose={onClose}
    >
      <div className="shortcut-help">
        {shortcutGroups.map((group) => (
          <section key={group.group}>
            <h3>{group.group}</h3>
            <dl className="shortcut-list">
              {group.shortcuts.map((shortcut) => (
                <div key={shortcut.chord}>
                  <dt>
                    <kbd>{shortcut.keys}</kbd>
                  </dt>
                  <dd>{shortcut.description}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </Modal>
  );
}
