"use client";

import { useState } from "react";
import { Link } from "react-router";

import {
  automationSentence,
  type AutomationRule,
  type AutomationRun,
  type AutomationRunResponse,
} from "../lib/domain";
import {
  useArchiveAutomationRule,
  useAutomationRules,
  useAutomationRuns,
  useCustomFields,
  useJobRuns,
  useRunAutomationRule,
} from "../lib/queries";
import { schedulerLine } from "../lib/jobs";
import { formatTimestamp } from "../lib/time";
import { PageHeader, useShellUser } from "./AppShell";
import { AutomationRuleForm } from "./AutomationRuleForm";
import { useConfirm } from "./ConfirmDialog";

/**
 * The automations screen at `/automations` (milestone 6.3,
 * `docs/FEATURES.md` §11).
 *
 * A screen rather than a panel, for the reason `/reports` and `/tasks` are:
 * a rule is about every deal at once, so there is no one deal to hang it off.
 *
 * Four things about what it shows:
 *
 * - **Every rule, not only yours** (D-173). A colleague's rule can move a
 *   deal you own, so "which automations run here, and whose" has to be
 *   answerable; the controls are hidden on a rule you did not write, because
 *   the API refuses them.
 * - **Preview before Run, and Preview is the prominent one.** §11 requires a
 *   rule be dry-runnable, and the preview names the deals it would touch and
 *   what it would do to each. Running for real asks for confirmation, because
 *   it writes to deals that are not on this screen.
 * - **The log is a disclosure per rule**, not a feed. The question is "what
 *   has this rule done", which is asked of one rule at a time — and it is the
 *   place a *skip* is read, which is the half a timeline cannot show: a rule
 *   that matched and declined leaves no entry anywhere else.
 * - **A skip states its reason.** "Editor may not change stage here" is the
 *   difference between a rule somebody can fix and a rule that silently does
 *   nothing.
 */
export function AutomationsPage() {
  // The shell resolves the session, so every query on this screen is enabled.
  const viewer = useShellUser();
  // Archived rules are off by default and reachable, because the reason the
  // row is kept at all is its run log: "rule 4 moved this deal" needs rule 4
  // to still be readable. Listing them beside the live ones would make the
  // screen a history instead of a list of what runs.
  const [showArchived, setShowArchived] = useState(false);
  const rules = useAutomationRules(true, showArchived);
  const customFields = useCustomFields("opportunity", true);
  const jobRuns = useJobRuns(true);
  const [editing, setEditing] = useState<AutomationRule | null>(null);
  const [composing, setComposing] = useState(false);

  const listed = rules.data ?? [];

  return (
    <main className="app-shell">
      <section className="workspace">
        <PageHeader
          title="Automations"
          subtitle={
            <p className="page-subtitle">
              Rules that watch for one thing and do one thing.
            </p>
          }
        >
          <button
            type="button"
            className="primary-button"
            onClick={() => setComposing(true)}
          >
            New rule
          </button>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(event) => setShowArchived(event.target.checked)}
            />
            Show archived rules
          </label>
        </PageHeader>

        <p className="report-note">
          A rule watches for one thing, checks your conditions, and does one
          thing. It runs on the deals you can see and does only what you could
          do yourself, and it never triggers another rule.
        </p>

        {/* When the clock last looked (milestone 6.5). On screen because the
            failure `docs/ARCHITECTURE.md` names -- a scheduler that silently
            stops -- is invisible from everywhere else: the rules simply never
            fire again, and this is the screen somebody would be standing on
            when they wondered why. */}
        {jobRuns.data && (
          <p className="report-note">{schedulerLine(jobRuns.data)}</p>
        )}

        {rules.isError && <p className="error">{rules.error.message}</p>}
        {rules.isPending && <p className="status">Loading rules...</p>}

        {rules.data && listed.length === 0 && (
          <p className="empty-state">
            No rules yet. A first one worth having: when nothing has happened on
            a deal for fourteen days, create a task to chase it.
          </p>
        )}

        <ul className="automation-list">
          {listed.map((rule) => (
            <RuleRow
              key={rule.id}
              rule={rule}
              mine={rule.created_by === viewer.id}
              onEdit={() => setEditing(rule)}
            />
          ))}
        </ul>
      </section>

      {(composing || editing) && (
        <AutomationRuleForm
          rule={editing}
          customFields={customFields.data ?? []}
          onClose={() => {
            setComposing(false);
            setEditing(null);
          }}
        />
      )}
    </main>
  );
}

function RuleRow({
  rule,
  mine,
  onEdit,
}: {
  rule: AutomationRule;
  mine: boolean;
  onEdit: () => void;
}) {
  const run = useRunAutomationRule();
  const archive = useArchiveAutomationRule();
  const confirm = useConfirm();
  const [preview, setPreview] = useState<AutomationRunResponse | null>(null);
  const [showLog, setShowLog] = useState(false);

  async function apply() {
    const agreed = await confirm({
      title: "Run this rule now?",
      description:
        "It will write to every deal it matches, which may not all be on " +
        "this screen. Preview first if you have not.",
      confirmLabel: "Run it",
    });
    if (agreed) {
      run.mutate({ id: rule.id, dryRun: false }, { onSuccess: setPreview });
    }
  }

  return (
    <li className="automation-rule">
      <div className="section-heading">
        <h2>{rule.name}</h2>
        <span>
          {rule.enabled ? "Enabled" : "Disabled"}
          {rule.archived_at === null ? "" : " - archived"}
          {mine ? "" : ` - ${rule.creator_name}'s`}
        </span>
      </div>

      <p className="automation-sentence">{automationSentence(rule)}</p>

      {mine && rule.archived_at === null && (
        <div className="inline-actions">
          <button
            type="button"
            onClick={() =>
              run.mutate(
                { id: rule.id, dryRun: true },
                { onSuccess: setPreview },
              )
            }
            disabled={run.isPending}
          >
            Preview
          </button>
          <button type="button" className="secondary-button" onClick={apply}>
            Run now
          </button>
          <button type="button" className="secondary-button" onClick={onEdit}>
            Edit
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() => archive.mutate(rule.id)}
          >
            Archive
          </button>
        </div>
      )}

      {run.isError && <p className="error">{run.error.message}</p>}
      {preview && <RunResult result={preview} />}

      <button
        type="button"
        className="disclosure-button"
        aria-expanded={showLog}
        onClick={() => setShowLog(!showLog)}
      >
        <span aria-hidden="true">{showLog ? "-" : "+"}</span>{" "}
        {showLog ? "Hide what it has done" : "What it has done"}
      </button>
      {showLog && <RunLog ruleId={rule.id} />}
    </li>
  );
}

/** The answer to one Preview or Run: what it considered, and what it decided
 * about each deal it matched. `considered` is on screen because "nothing
 * happened" has two meanings — no deal matched the trigger, or none passed the
 * conditions — and a reader fixing a rule needs to know which.
 *
 * It says **matched**, not "acted on": a matched deal can still be a skip
 * (the author lacks the role, or the action is already satisfied), and the
 * outcome per deal is what the list below says. A summary line that counted
 * skips as actions would be the one sentence on this screen that lies. */
function RunResult({ result }: { result: AutomationRunResponse }) {
  return (
    <div className="automation-preview">
      <p>
        {result.dry_run ? "Preview: " : "Ran: "}
        matched {result.runs.length} of {result.considered} deals
        {result.runs.length === 0
          ? "."
          : result.dry_run
            ? ", and would do this:"
            : ", and did this:"}
      </p>
      {result.runs.length > 0 && <RunList runs={result.runs} />}
    </div>
  );
}

function RunLog({ ruleId }: { ruleId: number }) {
  const runs = useAutomationRuns(ruleId);
  if (runs.isPending) {
    return <p className="status">Loading...</p>;
  }
  if (runs.isError) {
    return <p className="error">{runs.error.message}</p>;
  }
  if ((runs.data ?? []).length === 0) {
    return <p className="empty-state">This rule has not done anything yet.</p>;
  }
  return <RunList runs={runs.data ?? []} />;
}

function RunList({ runs }: { runs: AutomationRun[] }) {
  return (
    <ul className="automation-runs">
      {runs.map((item) => (
        <li key={item.id}>
          <Link to={`/opportunities/${item.opportunity_id}`}>
            {item.opportunity_name}
          </Link>
          <span className={`automation-outcome is-${item.outcome}`}>
            {item.outcome}
          </span>
          {item.reason && <span>{item.reason}</span>}
          <span className="meta">
            {formatTimestamp(item.created_at)}
            {item.dry_run ? " - preview" : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}
