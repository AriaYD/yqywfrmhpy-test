"use client";

import { useI18n, type MessageKey } from "@/i18n";
import type { Schemas } from "@/lib/api";
import { Card, Empty, SectionTitle } from "@/components/ui";

/**
 * R5-B/D（2026-08-01）：LinkedIn 式补充分区（教育 / 语言 / 出版物 /
 * 荣誉奖项 / 组织机构 / 兴趣爱好）——显示与编辑同一组件。
 * 这些分区整体是**自述**（学生自填自改）；来自 SIS/证据的分区
 * （校内课程、证书）各有出处与核验状态，不在这里自由编辑。
 */
export type Extras = Schemas["ProfileExtras"];
type Entry = Schemas["ProfileEntry"];

const inputCls = "field t-meta px-2 py-1.5";

function EntryRows({
  titleKey,
  rows,
  editing,
  onChange,
  tag,
}: {
  titleKey: MessageKey;
  rows: Entry[];
  editing: boolean;
  onChange: (rows: Entry[]) => void;
  tag: string;
}) {
  const { t } = useI18n();
  return (
    <Card data-extras-section={tag}>
      <SectionTitle>{t(titleKey)}</SectionTitle>
      {!editing && rows.length === 0 && <Empty messageKey="profile.extras.empty" />}
      <ul className="flex flex-col gap-2">
        {rows.map((row, index) => (
          <li key={index} className="flex flex-wrap items-baseline gap-2"
              data-extras-row={`${tag}-${index}`}>
            {!editing ? (
              <>
                <span className="t-body text-fg">
                  {row.url ? (
                    <a href={row.url} target="_blank" rel="noreferrer"
                       className="underline underline-offset-2"
                       style={{ color: "var(--accent-deep)" }}>
                      {row.title} ↗
                    </a>
                  ) : row.title}
                </span>
                {row.issuer && (
                  <span className="t-meta text-fg-muted">· {row.issuer}</span>
                )}
                {row.date && <span className="t-micro text-fg-faint">{row.date}</span>}
                {row.note && <span className="t-meta text-fg-muted">{row.note}</span>}
              </>
            ) : (
              <>
                {(["title", "issuer", "date", "url"] as const).map((field) => (
                  <input
                    key={field}
                    type="text"
                    data-extras-input={`${tag}-${index}-${field}`}
                    value={(row[field] as string | null) ?? ""}
                    placeholder={t(`profile.extras.${field}` as MessageKey)}
                    onChange={(e) =>
                      onChange(rows.map((r, i) =>
                        i === index ? { ...r, [field]: e.target.value || null } : r))
                    }
                    className={inputCls}
                    style={{ width: field === "title" ? "16rem" : "9rem" }}
                  />
                ))}
                <button
                  type="button"
                  data-extras-remove={`${tag}-${index}`}
                  onClick={() => onChange(rows.filter((_, i) => i !== index))}
                  className="pressable t-meta text-fg-faint"
                  aria-label="remove"
                >
                  ×
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
      {editing && (
        <button
          type="button"
          data-extras-add={tag}
          onClick={() =>
            onChange([...rows, { title: "", issuer: null, date: null,
                                 url: null, note: null }])
          }
          className="pressable btn btn-secondary t-meta mt-2"
        >
          + {t("profile.extras.addRow")}
        </button>
      )}
    </Card>
  );
}

export function ProfileExtrasSections({
  draft,
  editing,
  onChange,
}: {
  draft: Extras;
  editing: boolean;
  onChange: (next: Extras) => void;
}) {
  const { t } = useI18n();
  return (
    <>
      {/* Education */}
      <Card data-extras-section="education">
        <SectionTitle>{t("profile.section.education")}</SectionTitle>
        {!editing && draft.education.length === 0 && (
          <Empty messageKey="profile.extras.empty" />
        )}
        <ul className="flex flex-col gap-2">
          {draft.education.map((row, index) => (
            <li key={index} className="flex flex-wrap items-baseline gap-2"
                data-extras-row={`education-${index}`}>
              {!editing ? (
                <>
                  <span className="t-body font-medium text-fg">{row.school}</span>
                  {row.program && (
                    <span className="t-meta text-fg-muted">· {row.program}</span>
                  )}
                  <span className="t-micro text-fg-faint">
                    {row.start_year ?? ""}{row.end_year ? ` → ${row.end_year}` : ""}
                  </span>
                  {row.note && <span className="t-meta text-fg-muted">{row.note}</span>}
                </>
              ) : (
                <>
                  {(["school", "program", "start_year", "end_year", "note"] as const)
                    .map((field) => (
                    <input
                      key={field}
                      type="text"
                      data-extras-input={`education-${index}-${field}`}
                      value={(row[field] as string | null) ?? ""}
                      placeholder={t(`profile.extras.${field}` as MessageKey)}
                      onChange={(e) =>
                        onChange({
                          ...draft,
                          education: draft.education.map((r, i) =>
                            i === index
                              ? { ...r, [field]: e.target.value || null }
                              : r),
                        })
                      }
                      className={inputCls}
                      style={{ width: field === "school" || field === "program"
                        ? "13rem" : "6rem" }}
                    />
                  ))}
                  <button
                    type="button"
                    data-extras-remove={`education-${index}`}
                    onClick={() =>
                      onChange({
                        ...draft,
                        education: draft.education.filter((_, i) => i !== index),
                      })
                    }
                    className="pressable t-meta text-fg-faint"
                  >
                    ×
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
        {editing && (
          <button
            type="button"
            data-extras-add="education"
            onClick={() =>
              onChange({
                ...draft,
                education: [...draft.education, {
                  school: "", program: null, start_year: null,
                  end_year: null, note: null,
                }],
              })
            }
            className="pressable btn btn-secondary t-meta mt-2"
          >
            + {t("profile.extras.addRow")}
          </button>
        )}
      </Card>

      {/* Publications / Honors / Organizations —— 同构条目 */}
      <EntryRows titleKey="profile.section.publications" tag="publications"
                 rows={[...draft.publications]} editing={editing}
                 onChange={(rows) => onChange({ ...draft, publications: rows })} />
      <EntryRows titleKey="profile.section.honors" tag="honors"
                 rows={[...draft.honors]} editing={editing}
                 onChange={(rows) => onChange({ ...draft, honors: rows })} />
      <EntryRows titleKey="profile.section.organizations" tag="organizations"
                 rows={[...draft.organizations]} editing={editing}
                 onChange={(rows) => onChange({ ...draft, organizations: rows })} />

      {/* Languages */}
      <Card data-extras-section="languages">
        <SectionTitle>{t("profile.section.languages")}</SectionTitle>
        {!editing && draft.languages.length === 0 && (
          <Empty messageKey="profile.extras.empty" />
        )}
        <ul className="flex flex-col gap-2">
          {draft.languages.map((row, index) => (
            <li key={index} className="flex flex-wrap items-baseline gap-2"
                data-extras-row={`languages-${index}`}>
              {!editing ? (
                <>
                  <span className="t-body text-fg">{row.language}</span>
                  <span className="t-meta text-fg-muted">· {row.proficiency}</span>
                  {row.certification && (
                    <span className="t-micro text-fg-faint">{row.certification}</span>
                  )}
                </>
              ) : (
                <>
                  {(["language", "proficiency", "certification"] as const)
                    .map((field) => (
                    <input
                      key={field}
                      type="text"
                      data-extras-input={`languages-${index}-${field}`}
                      value={(row[field] as string | null) ?? ""}
                      placeholder={t(`profile.extras.${field}` as MessageKey)}
                      onChange={(e) =>
                        onChange({
                          ...draft,
                          languages: draft.languages.map((r, i) =>
                            i === index
                              ? { ...r, [field]: e.target.value || null }
                              : r),
                        })
                      }
                      className={inputCls}
                    />
                  ))}
                  <button
                    type="button"
                    data-extras-remove={`languages-${index}`}
                    onClick={() =>
                      onChange({
                        ...draft,
                        languages: draft.languages.filter((_, i) => i !== index),
                      })
                    }
                    className="pressable t-meta text-fg-faint"
                  >
                    ×
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
        {editing && (
          <button
            type="button"
            data-extras-add="languages"
            onClick={() =>
              onChange({
                ...draft,
                languages: [...draft.languages,
                            { language: "", proficiency: "", certification: null }],
              })
            }
            className="pressable btn btn-secondary t-meta mt-2"
          >
            + {t("profile.extras.addRow")}
          </button>
        )}
      </Card>

      {/* Interests（爱好，与专业无关） */}
      <Card data-extras-section="hobbies">
        <SectionTitle>{t("profile.section.hobbies")}</SectionTitle>
        <div className="flex flex-wrap items-center gap-2">
          {draft.hobbies.map((hobby, index) => (
            <span key={index}
                  className="t-meta flex items-center gap-1 rounded-sm border border-line px-2.5 py-1 text-fg-muted">
              {hobby}
              {editing && (
                <button
                  type="button"
                  data-extras-remove={`hobbies-${index}`}
                  onClick={() =>
                    onChange({
                      ...draft,
                      hobbies: draft.hobbies.filter((_, i) => i !== index),
                    })
                  }
                  className="pressable text-fg-faint"
                >
                  ×
                </button>
              )}
            </span>
          ))}
          {!editing && draft.hobbies.length === 0 && (
            <span className="t-meta text-fg-faint">{t("profile.extras.empty")}</span>
          )}
          {editing && (
            <input
              type="text"
              data-extras-input="hobbies-new"
              placeholder={t("profile.extras.addHobby")}
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                const value = (e.target as HTMLInputElement).value.trim();
                if (value && !draft.hobbies.includes(value)) {
                  onChange({ ...draft, hobbies: [...draft.hobbies, value] });
                }
                (e.target as HTMLInputElement).value = "";
              }}
              className={inputCls}
            />
          )}
        </div>
      </Card>
    </>
  );
}
