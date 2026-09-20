"use client";

import { useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";

import { filterCommands, type Command } from "../lib/palette";
import { useLogout, useOpportunities } from "../lib/queries";
import { Modal } from "./Modal";

/**
 * The command palette (`docs/FEATURES.md` §12): jump to an opportunity, switch
 * screen, run an action, or fall through to full-text search.
 *
 * Mounted only while it is open, so the opportunity list it jumps to is
 * fetched on Ctrl K rather than on every page load. The list itself is the one
 * the board already reads, so opening the palette on the dashboard costs
 * nothing — it is the same cache entry.
 */
export function CommandPalette({
  onClose,
  onShowShortcuts,
}: {
  onClose: () => void;
  onShowShortcuts: () => void;
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const navigate = useNavigate();
  const opportunities = useOpportunities(true);
  const logout = useLogout();

  // `onClose` rather than the dialog's own dismiss: the reader is on another
  // screen now, so handing focus back to the control they opened the palette
  // from would put them behind where they are (`Modal`).
  function go(path: string) {
    onClose();
    navigate(path);
  }

  const commands: Command[] = [
    {
      id: "dashboard",
      label: "Go to the dashboard",
      hint: "The pipeline board",
      run: () => go("/"),
    },
    { id: "search", label: "Go to search", run: () => go("/search") },
    ...(opportunities.data ?? []).map((opportunity) => ({
      id: `opportunity-${opportunity.id}`,
      label: opportunity.name,
      hint: `${opportunity.account_name} | ${opportunity.stage}`,
      run: () => go(`/opportunities/${opportunity.id}`),
    })),
    {
      id: "shortcuts",
      label: "Show keyboard shortcuts",
      run: () => {
        onClose();
        onShowShortcuts();
      },
    },
    {
      id: "sign-out",
      label: "Sign out",
      run: () => {
        onClose();
        logout.mutate();
      },
    },
  ];

  const trimmed = query.trim();
  const matches = filterCommands(commands, query);
  if (trimmed) {
    // Search is the fallthrough rather than a match, so it is offered even
    // when the query already found an opportunity by name.
    matches.push({
      id: "search-everything",
      label: `Search everything for "${trimmed}"`,
      run: () => go(`/search?q=${encodeURIComponent(trimmed)}`),
    });
  }

  const active = matches[Math.min(activeIndex, matches.length - 1)];

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActiveIndex((current) => {
        const next = Math.min(current, matches.length - 1) + step;
        return (next + matches.length) % Math.max(matches.length, 1);
      });
      return;
    }
    if (event.key === "Enter" && active) {
      event.preventDefault();
      active.run();
    }
  }

  return (
    <Modal label="Command palette" onClose={onClose}>
      <div className="palette">
        <input
          className="palette-input"
          type="text"
          role="combobox"
          aria-expanded="true"
          aria-controls="command-palette-list"
          aria-autocomplete="list"
          aria-activedescendant={active ? `command-${active.id}` : undefined}
          aria-label="Run a command, jump to an opportunity, or search"
          placeholder="Type a command or an opportunity name"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(0);
          }}
          onKeyDown={onKeyDown}
        />

        <ul
          className="palette-list"
          id="command-palette-list"
          role="listbox"
          aria-label="Commands"
        >
          {matches.map((command) => (
            <li
              key={command.id}
              id={`command-${command.id}`}
              role="option"
              aria-selected={command.id === active?.id}
              className={
                command.id === active?.id
                  ? "palette-option active"
                  : "palette-option"
              }
              onMouseDown={(event) => event.preventDefault()}
              onClick={command.run}
            >
              <span>{command.label}</span>
              {command.hint && <span className="hint">{command.hint}</span>}
            </li>
          ))}
        </ul>

        {matches.length === 0 && (
          <p className="empty-state">Nothing matches that.</p>
        )}
      </div>
    </Modal>
  );
}
