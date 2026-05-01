'use client';

import { useState } from 'react';
import { BrainCircuit, Check, Sparkles, X } from 'lucide-react';
import type { PublishedSkill, SkillCandidate } from '@/lib/types';

interface Props {
  candidates: SkillCandidate[];
  publishedSkills: PublishedSkill[];
  loading?: boolean;
  onApprove: (candidate: SkillCandidate, payload?: { review_notes?: string; edited_title?: string; edited_instructions?: string }) => Promise<void>;
  onReject: (candidate: SkillCandidate, reviewNotes?: string) => Promise<void>;
}

export default function LearningPanel({
  candidates,
  publishedSkills,
  loading = false,
  onApprove,
  onReject,
}: Props) {
  return (
    <div className="flex-1 overflow-y-auto thin-scroll p-5 space-y-6">
      <section className="rounded-[28px] border border-slate-200 bg-white/85 shadow-[0_20px_60px_rgba(15,23,42,0.06)] backdrop-blur">
        <div className="border-b border-slate-100 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-emerald-50 p-2 text-emerald-600">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Learning Queue</h2>
              <p className="text-xs text-slate-500">Patterns detected from successful SQL + manual corrections</p>
            </div>
          </div>
        </div>
        <div className="space-y-4 p-5">
          {candidates.length === 0 && (
            <EmptyState
              title="No skill candidates yet"
              body="Once the agent sees repeated successful patterns, they will show up here for manual review."
            />
          )}
          {candidates.map((candidate) => (
            <CandidateCard
              key={candidate.id}
              candidate={candidate}
              loading={loading}
              onApprove={onApprove}
              onReject={onReject}
            />
          ))}
        </div>
      </section>

      <section className="rounded-[28px] border border-slate-200 bg-white/85 shadow-[0_20px_60px_rgba(15,23,42,0.06)] backdrop-blur">
        <div className="border-b border-slate-100 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-sky-50 p-2 text-sky-600">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Published Skills</h2>
              <p className="text-xs text-slate-500">Manually approved business patterns used during SQL generation</p>
            </div>
          </div>
        </div>
        <div className="grid gap-4 p-5 md:grid-cols-2">
          {publishedSkills.length === 0 && (
            <EmptyState
              title="Nothing published yet"
              body="Approved skills will appear here and start influencing similar queries."
            />
          )}
          {publishedSkills.map((skill) => (
            <article
              key={skill.id}
              className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4"
            >
              <div className="mb-2 flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-slate-900">{skill.title}</h3>
                <span className="rounded-full bg-sky-100 px-2.5 py-1 text-[11px] font-medium text-sky-700">
                  active
                </span>
              </div>
              <p className="text-sm leading-6 text-slate-600">{skill.summary}</p>
              {skill.metadata?.selected_tables?.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {skill.metadata.selected_tables.slice(0, 4).map((table) => (
                    <span
                      key={table}
                      className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-slate-200"
                    >
                      {table}
                    </span>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function CandidateCard({
  candidate,
  loading,
  onApprove,
  onReject,
}: {
  candidate: SkillCandidate;
  loading: boolean;
  onApprove: (candidate: SkillCandidate, payload?: { review_notes?: string; edited_title?: string; edited_instructions?: string }) => Promise<void>;
  onReject: (candidate: SkillCandidate, reviewNotes?: string) => Promise<void>;
}) {
  const [title, setTitle] = useState(candidate.title);
  const [instructions, setInstructions] = useState(candidate.metadata?.instructions || '');
  const [notes, setNotes] = useState(candidate.metadata?.review_notes || '');

  return (
    <article className="rounded-3xl border border-amber-200 bg-gradient-to-br from-amber-50 via-white to-orange-50 p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700">
            Candidate #{candidate.id}
          </p>
          <h3 className="mt-1 text-base font-semibold text-slate-900">{candidate.title}</h3>
        </div>
        <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-amber-700 ring-1 ring-amber-200">
          confidence {(candidate.confidence * 100).toFixed(0)}%
        </span>
      </div>

      <p className="text-sm leading-6 text-slate-600">{candidate.summary}</p>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <Field label="Trigger question">
          <div className="rounded-2xl bg-white/85 p-3 text-sm text-slate-700 ring-1 ring-amber-100">
            {candidate.trigger_query}
          </div>
        </Field>
        <Field label="Representative tables">
          <div className="flex flex-wrap gap-2 rounded-2xl bg-white/85 p-3 ring-1 ring-amber-100">
            {(candidate.metadata?.selected_tables || []).slice(0, 6).map((table) => (
              <span
                key={table}
                className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-800"
              >
                {table}
              </span>
            ))}
          </div>
        </Field>
      </div>

      <div className="mt-4 grid gap-3">
        <Field label="Editable skill title">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-amber-300 focus:ring-4 focus:ring-amber-100"
          />
        </Field>
        <Field label="Instructions the model should follow">
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={4}
            className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-800 outline-none focus:border-amber-300 focus:ring-4 focus:ring-amber-100"
          />
        </Field>
        <Field label="Reviewer notes">
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional notes about when to use or avoid this skill"
            className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-amber-300 focus:ring-4 focus:ring-amber-100"
          />
        </Field>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          onClick={() => onApprove(candidate, { edited_title: title, edited_instructions: instructions, review_notes: notes })}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-2xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
        >
          <Check className="h-4 w-4" />
          Publish skill
        </button>
        <button
          onClick={() => onReject(candidate, notes)}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-2xl bg-white px-4 py-2 text-sm font-semibold text-rose-600 ring-1 ring-rose-200 transition hover:bg-rose-50 disabled:opacity-50"
        >
          <X className="h-4 w-4" />
          Reject
        </button>
      </div>
    </article>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
        {label}
      </span>
      {children}
    </label>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 p-6 text-center">
      <p className="text-sm font-semibold text-slate-700">{title}</p>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">{body}</p>
    </div>
  );
}
