# 05 - Frontend Audit

Branch: `chore/revive-local-docker-setup` (HEAD `f891313`). Scope: `frontend/`, compared against `backend/app/schemas/response.py` and the routes it serves. Uncommitted working-tree edits were audited as they stand in `frontend/components/interviewer/compatibility-score.tsx`, `skill-gaps.tsx`, `skills-assessment.tsx` and `backend/app/schemas/response.py`. No application code was changed.

Note: the backend "schema" is not Pydantic. It is two plain JSON-Schema dicts (`candidate_schema`, `interviewer_schema`) that go to Gemini as `response_json_schema` (`backend/app/service/llm/gemini.py:20-31`). The task result is returned as-is, with no validation step (`backend/app/service/interview_cheatsheet.py:16-20`, `backend/app/tasks/cheatsheet_tasks.py:9-33`).

---

## 1. What exists

### 1.1 Framework and build
| Item | Finding | Ref |
|---|---|---|
| Next.js | `15.5.28` (installed version matches), React `^19` | `frontend/package.json:52-55`, `node_modules/next/package.json:3` |
| Router | App Router only (`app/`), no `pages/` | `frontend/app/*` |
| Rendering | Almost everything is `"use client"`. Only `app/generate/page.tsx` and `app/layout.tsx` are server components | `app/page.tsx:1`, `app/results/[id]/page.tsx:1`, `app/profile/page.tsx:1` |
| Build safety | `typescript.ignoreBuildErrors: true`, `eslint.ignoreDuringBuilds: true` | `frontend/next.config.mjs:4-9` |
| TS | `strict: true`, but `tsc --noEmit` reports only 1 error (`components/navbar.tsx(64,14)`), because result data is typed `any` throughout | `frontend/tsconfig.json:7` |
| Deps | 20+ dependencies pinned to `"latest"` (`zod`, `react-hook-form`, `@radix-ui/*`, `date-fns`, `react-dropzone`) | `frontend/package.json:12-66` |
| Error/loading routes | No `error.tsx`, `loading.tsx` or `not-found` handling per route; only `app/not-found.tsx` | `frontend/app/` |

### 1.2 Redux store
| Slice | State | Ref |
|---|---|---|
| `auth` | `accessToken`, `expiryTime`, hydrated from `localStorage` at module load; thunks `loginAndStartTimer`, `logoutAndClearTimer`, `initializeAuth` | `redux/slices/authSlice.ts:16-115` |
| `user` | flat profile fields | `redux/slices/userSlice.ts:3-45` |
| `cheatsheets` | `cheatsheets[]`, `currentCheatsheet`. No `status`/`error` fields. `content: string`, `id: string` | `redux/slices/cheatsheetSlice.ts:3-20` |
| Store | `configureStore`, module singleton, not persisted | `redux/store.ts:6-12`, `components/redux-provider.tsx:5-8` |
| `redux/index.ts` | empty file | `redux/index.ts` |

### 1.3 API layer
- Base URL: `apiBaseURL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"` (`utils.ts:12`). It is baked in at build time (`frontend/Dockerfile:10-11`, `docker-compose.yml:56`).
- There is no API client module. Each caller runs raw `fetch` and builds its own `Authorization` header:
  - `components/layout.tsx:17-47` loads `/user/details` and `/user/cheatsheets` whenever the token changes (`:49-69`).
  - `components/auth/login-form.tsx:81-111` runs the same two fetches again after login (`:122-125`).
  - `components/cheatsheet-generator.tsx:39-52` (poll) and `:96-100` (submit).
- Dead code: `utils.ts:14-32` `fetchWithAuth`, plus `constant/api.ts:1-43`, `constant/interface.ts:1-76`, `lib/mock-*.ts`. Nothing imports them.

### 1.4 Async job flow (polling)
`cheatsheet-generator.tsx:96-114`: POST `/cheatsheet/generate` returns `task_id`. `pollTask` then GETs `/cheatsheet/task-status/{id}` every 3 s, for up to 5 min (`:39-52`). On `SUCCESS` it dispatches `addCheatsheet` and `setCurrentCheatsheet` (`:110-111`) and routes to `/results/{id}` (`:114`). `FAILURE` throws `status.error` (`:49`). The backend contract matches (`backend/app/routes/cheatsheet.py:51-64`).

### 1.5 Dashboard mapping (intended section -> component -> backend key)
| User | Intended section | Component | Backend key | Ref |
|---|---|---|---|---|
| Seeker | Resume SWOT | `SwotAnalysis` | `swot_analysis` | `components/swot-analysis.tsx`, `response.py:13-63` |
| Seeker | Skill Gap Analysis | `SkillAssessment` (missing/partial lists) | `skill_assessment` | `components/skill-assessment.tsx`, `response.py:64-110` |
| Seeker | Learning Recommendations | **none** (only a "Watch Video" link inside Concept Refresh) | `concept_refresh[].video_resource` | `components/concept-refresh.tsx:79-87` |
| Seeker | Concept Revision Areas | `ConceptRefresh` | `concept_refresh` | `components/concept-refresh.tsx`, `response.py:111-146` |
| Seeker | Predicted Interview Questions | `InterviewQuestions` | `interview_questions` | `components/interview-questions.tsx`, `response.py:147-166` |
| Seeker | Company Insights | `CompanyInsights` | `company_insights` | `components/company-insights.tsx`, `response.py:167-188` |
| Interviewer | Candidate Summary | `CandidateOverview` | `candidate_overview` | `components/interviewer/candidate-overview.tsx`, `response.py:204-219` |
| Interviewer | Experience Analysis / Education Review | `EducationExperience` (two tabs) | `experience`, `education` | `components/interviewer/education-experience.tsx`, `response.py:281-316` |
| Interviewer | Job Compatibility Score | `CompatibilityScore` | `compatibility_score` | `components/interviewer/compatibility-score.tsx`, `response.py:220-232` |
| Interviewer | Skill Assessment | `SkillsAssessment` | `skills_assessment.data` | `components/interviewer/skills-assessment.tsx`, `response.py:233-280` |
| Interviewer | Skill Gap Detection | `SkillGaps` | `skill_gaps_and_concerns` | `components/interviewer/skill-gaps.tsx`, `response.py:317-329` |
| Interviewer | Potential Concerns | **no dedicated component**: `concerns[]` list inside `InterviewRecommendation` | `interview_recommendation.concerns` | `interview-recommendation.tsx:104-113` |
| Interviewer | Recommended Screening Questions | `ScreeningQuestions` | `recommended_screening_questions` | `components/interviewer/screening-questions.tsx`, `response.py:330-342` |
| Interviewer | Interview Strategy | `InterviewRecommendation` (proceed verdict + next steps) | `interview_recommendation` | `interview-recommendation.tsx`, `response.py:343-362` |

The results page picks the dashboard by `cheatsheet_type` and reshapes `content` with `(sheet.content as any)` casts (`app/results/[id]/page.tsx:41-84`).

---

## 2. Gaps vs intended architecture

1. **Learning Recommendations is not a section.** The candidate schema has two `"items"` keys under `concept_refresh` (`response.py:113-129` and `:130-145`). The second one silently overwrites the first in the Python dict, so `article_resource` never reaches Gemini, and only a single `video_resource` URL survives. The UI renders it as one unvalidated link (`concept-refresh.tsx:79-87`).
2. **Potential Concerns and Interview Strategy are not separate sections.** Concerns appear only as a bullet list inside the recommendation card (`interview-recommendation.tsx:104-113`). "Strategy" is just `proceed` + `recommended_next_steps`. The schema has no field for interview flow, time allocation or focus areas (`response.py:343-362`).
3. **Experience Analysis is thin.** Each role shows only a `relevance_to_job` badge (`education-experience.tsx:34-48`). The schema has no gap or tenure analysis (`response.py:298-316`).
4. **No shared contract types.** The real `Cheatsheet.content` is a JSON object (`backend/app/db/models.py:49`, `routes/user.py:59`), but it is typed `string` (`cheatsheetSlice.ts:7`). Every component declares its own local interface. The one central type file is unused and wrong: it has `concept`/`explanation` instead of `topic`/`review_notes`, and `string[]` SWOT entries where the backend uses `{title, description}` (`constant/interface.ts:18-46`).
5. **No fetch-by-id.** `/results/[id]` reads only from Redux (`app/results/[id]/page.tsx:20-22`) and depends on `layout.tsx:35-43` having loaded every cheatsheet first. The backend has no GET-by-id endpoint (see `docs/ARCHITECTURE.md:162`).
6. **No real job progress.** The loading screen shows four hard-coded steps with fixed bar widths (`components/loading.tsx:19-67`). The backend reports only Celery state (`routes/cheatsheet.py:54`).
7. **Export/print/share/feedback are stubs.** None of these buttons has an `onClick` (`results/candidate.cheatsheet.tsx:31-54,81-98`; `results/interview-cheatsheet.tsx:35-50,91-108`). `html2pdf.js` is installed but never imported (`package.json:47`).
8. **The refresh token is unused.** The backend issues and rotates refresh tokens (`backend/app/routes/auth.py:197-252`). The frontend stores only the access token and sends the user to login when it expires.

---

## 3. Bugs and risks

### 3.1 Crashes from missing fields (no defensive rendering, no error boundary)
`interviewer_schema` has **no top-level `required` list** (`response.py:201-363`), so Gemini may leave out any section. There is no `error.tsx` or React error boundary, so one bad field blanks the whole page.
| Location | Unguarded access | Trigger |
|---|---|---|
| `interview-recommendation.tsx:120` | `data.recommended_next_steps.map` | field is **optional** in schema (`response.py:361`), so this is a live crash path |
| `compatibility-score.tsx:45` | `formatScore(data.cultural_fit_score)` | optional field (`response.py:230`), renders `NaN%` |
| `app/results/[id]/page.tsx:71` | `content.candidate_overview.top_skills` | section omitted |
| `results/interview-cheatsheet.tsx:21,67,74` | `sheet.candidate.full_name`, `sheet.skillAssessment.data` | section omitted |
| `skills-assessment.tsx:192` | `data.skillsByCategory[0].category` | empty array |
| `skills-assessment.tsx:128,153-168` | `x / total` | all distribution counts 0, giving `NaN%` widths |
| `skill-gaps.tsx:21`, `screening-questions.tsx:76`, `education-experience.tsx:79,103` | `data.filter` / `.map` on possibly undefined arrays | section omitted |
| `swot-analysis.tsx:54,69,86,101` | `data?.strengths.map` (optional chain stops one level short) | quadrant omitted |
| `company-insights.tsx:76` | `data?.culture_points.length` | same pattern |
| `profile/cheatsheets-panel.tsx:37-38,64-67` | `content.company_insights.company_overview`, `content.candidate_overview.full_name`, `content.interview_recommendation.proceed` | **one malformed sheet crashes the whole profile page** |

### 3.2 Schema-to-UI mismatches
- **Interview question colour bar never renders.** The backend enum is capitalized (`"Technical"`, ...) (`response.py:155`), but `getCategoryIcon` matches lowercase (`interview-questions.tsx:51-64`).
- **Profile recommendation badge is mostly blank.** It matches `"Proceed"`/`"Reject"`/`"Consider"` (`profile/cheatsheets-panel.tsx:92-103`). The backend enum is `"Strong Yes"|"Yes"|"Consider"|"No"` (`response.py:346`), so only `Consider` shows a badge.
- **Wrong label for project questions.** `"project"` screening questions are labelled "Cultural Fit" (`screening-questions.tsx:40-41`). `"cultural"` is not in the backend enum (`response.py:336`), and the TS union literal is malformed: `"cultural | project"` (`screening-questions.tsx:12`).
- **Skill dots can come out empty.** Candidate `skill.rating` is a free string (`response.py:80,91`), but the stars map only `High|Medium|Low` (`skill-assessment.tsx:39-46`). Any other value renders 0 filled dots.
- **`match` is ignored.** The backend `match` enum is never read. The verdict comes from thresholds instead (`compatibility-score.tsx:31-36`), and the overall number is always teal (`:67`).
- **Social links never show.** `website`/`linkedin`/`github` are rendered (`candidate-overview.tsx:75-113`) but are not in the schema (`response.py:206-217`).
- **Required level is not drawn.** `required` appears only as text; the bars show `level` only (`skills-assessment.tsx:97-124`).

### 3.3 Working-tree changes (uncommitted)
- **Score-scale guess in `compatibility-score.tsx:39`.** `score <= 1 ? score * 100 : score` is ambiguous. A real 0-100 score of `1` (or `0.5`) is shown as 100% (or 50%). The schema now says 0-100 (`response.py:223-228`), so the guess only exists to keep legacy rows readable. A version or scale marker stored with each cheatsheet would be safer.
- **Level-scale guess in `skills-assessment.tsx:91-95`.** It applies x5 when *every* level and required value is `<= 1`. A weak new-format candidate (all levels 0-1 on the 0-5 scale, with all `required` values at 1 or less) gets multiplied by 5 and shown as expert. An empty `skillsByCategory` also returns `true`, which is harmless, but line 192 still crashes on that case.
- **`skill-gaps.tsx:104`: the label fix is correct, but the layout is still broken.** "Critical Gaps" became "Minor Gaps", as it should. But the minor-gap cards sit outside an empty `<div className="space-y-4"></div>` (`:107`), so they have no spacing, and the heading is still red (`:102`).
- **`backend/app/schemas/response.py`:** adds `minimum`/`maximum` bounds (`:68-71,223-228,251-252`). This is fine, but the duplicate `concept_refresh.items` key (`:113-145`) is still there.

### 3.4 API, auth and state
- **`fetchWithAuth` would crash if it were ever used.** It calls `useSelector` outside a component, which throws "Invalid hook call" (`utils.ts:15`). It is currently dead code, so there is **no central 401 handling**. A 401 on poll surfaces as "Failed to check cheatsheet status" (`cheatsheet-generator.tsx:46`).
- **Client and server session lengths differ.** The client session is 60 min (`authSlice.ts:7`); the server token lasts 90 min (`backend/app/routes/auth.py:21`). There is no refresh. `initializeAuth` is never dispatched (only defined at `authSlice.ts:98`), so after a reload the auto-logout timer does not run until the token changes.
- **Token is in `localStorage`** (`authSlice.ts:18,56`). Any XSS can read it.
- **SSR/CSR hydration mismatch.** The store is created during SSR with an empty token, while the client copy reads `localStorage` (`authSlice.ts:16-41`). The result differs between server HTML and client render in `app/page.tsx:14-17` (link href) and `hoc/withAuth.tsx:26-30`.
- **`/generate` is not auth-guarded** (`app/generate/page.tsx:11-18`). A guest can fill the form, sends `Authorization: Bearer ` with an empty token (`cheatsheet-generator.tsx:99`), and gets a 401 toast.
- **The redirect parameter is dropped.** `withAuth` redirects to `/?redirect=...` (`hoc/withAuth.tsx:17,22`), but nothing reads `redirect`. Login always pushes to `/generate` (`login-form.tsx` `onSubmit`, `router.push("/generate")`).
- **Double fetch on login.** `login-form.tsx:122-125` fetches user and cheatsheets, then the token change re-triggers `layout.tsx:49-69`, which fetches them again.
- **Logout leaves the previous user's cheatsheets in the store.** Logout clears auth (and `layout.tsx:51-53` clears user details), but `clearCheatsheets` is never dispatched. Until the next fetch, the store keeps the previous account's data, and `/results/{oldId}` reads from it.
- **`navbar.tsx:23,64`** uses an untyped `useDispatch()` to dispatch a thunk. This is the single `tsc` error.
- **`next/head` does nothing in the App Router** (`components/layout.tsx:9,73-75`).
- **Debug leftovers:** hard-coded ids `Number(27)` (`app/profile/page.tsx:21`) and `"5"` (`profile/cheatsheets-panel.tsx:43`), and `console.log` of full cheatsheet payloads (`app/results/[id]/page.tsx:23,59,82`; `swot-analysis.tsx:23`; `skills-assessment.tsx:37`; `interview-recommendation.tsx:18`).

### 3.5 Loading, error and empty states
- **Blank results page.** While `layout.tsx` is still fetching, or when the id is unknown or the type unexpected, the page returns `undefined`. The not-found toast/redirect and the "Unknown type" fallback are commented out (`app/results/[id]/page.tsx:25-39,86-90`).
- **No loading or error state in Redux.** List fetch errors are only `console.error` (`layout.tsx:28-30,44-46`). The profile then shows "No cheatsheets found" even when the fetch failed (`profile/cheatsheets-panel.tsx:71-90`). Its CTA also links to `/` rather than `/generate` (`:85`).
- **Empty sections are not handled.** Section cards render headings with nothing under them and no "none identified" text (`swot-analysis.tsx`, `skill-assessment.tsx:88-140`, `skill-gaps.tsx:64-129` renders an empty card when both lists are empty). The questions header renders `" Questions"` when `data` is undefined (`interview-questions.tsx:79`).
- **Polling problems** (`cheatsheet-generator.tsx:39-52`):
  - There is no `AbortController` or unmount cancel, so the loop keeps running after the user navigates away.
  - One network error or a 5xx aborts the poll even though the Celery task keeps running. The user is told it failed, but the cheatsheet appears later in the profile.
  - An unknown or expired `task_id` stays `PENDING` until the full 5-minute timeout.
  - The interval is fixed, with no backoff.
- **Removing the file does not reset the parent.** `removeFile` clears only local state (`file-uploader.tsx:81-84`), so `uploadedFile` in the parent (`cheatsheet-generator.tsx:26,187`) still holds the removed file, and submit sends it. `onDrop` deps also omit `onFileSelect` (`file-uploader.tsx:68`), and there is a fake 1 s "Uploading..." delay (`:55-65`).
- **Role toggle is not keyboard-accessible.** It uses clickable `<div>`s, not buttons (`cheatsheet-generator.tsx:155-177`).

### 3.6 Output-trust risks
- **LLM-supplied URLs are rendered without validation** (`concept-refresh.tsx:80`, `candidate-overview.tsx:79,92,105`). React 19 blocks `javascript:` URLs, but hallucinated or empty `href`s are shown as working links.

---

## 4. Prioritized fixes

| # | Pri | Fix | Effort | Files |
|---|---|---|---|---|
| 1 | P0 | Add `app/results/[id]/error.tsx` plus per-section error boundaries, so one bad field no longer blanks the dashboard | S | `app/results/[id]/`, `components/results/*.tsx` |
| 2 | P0 | Guard every array/object access with defaults (`?? []`, `?.`), and render "Not available" for missing sections. Start with `interview-recommendation.tsx:120` and `compatibility-score.tsx:45` (both are optional in the schema) | M | `components/interviewer/*.tsx`, `components/{swot-analysis,skill-assessment,company-insights,concept-refresh,interview-questions}.tsx`, `app/results/[id]/page.tsx:63-81`, `components/results/interview-cheatsheet.tsx:21-22,67,74` |
| 3 | P0 | Make the profile list defensive, since one malformed sheet currently crashes `/profile` | S | `components/profile/cheatsheets-panel.tsx:31-69` |
| 4 | P0 | Results page: add loading, not-found and unknown-type states instead of returning `undefined`; fetch by id when the item is not in the store (needs a backend `GET /user/cheatsheets/{id}`) | M | `app/results/[id]/page.tsx:20-90`, `backend/app/routes/user.py` |
| 5 | P1 | Add a top-level `required` list to `interviewer_schema`, and require `recommended_next_steps` and `cultural_fit_score`. Remove the duplicate `concept_refresh.items` key (keep both `video_resource` and `article_resource`) | S | `backend/app/schemas/response.py:113-145,201-363` |
| 6 | P1 | Add one typed contract (`types/cheatsheet.ts`) generated from or mirroring `response.py`. Type `Cheatsheet.content` as `CandidateContent \| InterviewerContent` keyed on `cheatsheet_type`, then remove the `as any` casts and `constant/interface.ts`. Consider zod parsing at the fetch boundary (zod is already a dep) | M | `redux/slices/cheatsheetSlice.ts:3-10`, `app/results/[id]/page.tsx`, `constant/interface.ts`, all section components |
| 7 | P1 | Fix enum mismatches: category case in `interview-questions.tsx:51-64`; recommendation badge in `profile/cheatsheets-panel.tsx:92-103`; "project" label and union in `screening-questions.tsx:12,40-41`; free-string `rating` in `skill-assessment.tsx:39-46` | S | listed files |
| 8 | P1 | Replace the scale guesses with an explicit `schema_version` (or scale) stored with each cheatsheet, and normalize legacy rows in one mapper. Until then, document that 0-1 values are ambiguous | M | `components/interviewer/compatibility-score.tsx:39`, `components/interviewer/skills-assessment.tsx:91-95`, `backend/app/tasks/cheatsheet_tasks.py:156-174` |
| 9 | P1 | Build one API client: base URL, auth header from `store.getState()`, central 401 handling with refresh-token retry, and parsed errors. Delete `utils.ts:14-32` and `constant/api.ts`. Align session length with server `exp` (decode JWT `exp` instead of a fixed 60 min) | M | `utils.ts`, `redux/slices/authSlice.ts:7,83-96`, `components/layout.tsx`, `components/auth/login-form.tsx`, `components/cheatsheet-generator.tsx` |
| 10 | P1 | Make polling robust: abort on unmount, retry transient errors with backoff, handle 401/404 explicitly, and on timeout tell the user the sheet will appear in their profile | S | `components/cheatsheet-generator.tsx:39-52,95-127` |
| 11 | P1 | Guard `/generate` with `withAuth`, honour `?redirect=`, and dispatch `clearCheatsheets` on logout | S | `app/generate/page.tsx`, `hoc/withAuth.tsx:17,22`, `components/auth/login-form.tsx`, `redux/slices/authSlice.ts:74-81` |
| 12 | P1 | Fix the stale-file bug: `removeFile` must notify the parent | S | `components/file-uploader.tsx:81-84`, `components/cheatsheet-generator.tsx:185-188` |
| 13 | P2 | Add `status`/`error` to the cheatsheets slice (or move to RTK Query). Show a fetch-error state separate from the empty state. Fix the empty-state CTA to `/generate` | M | `redux/slices/cheatsheetSlice.ts`, `components/layout.tsx:33-47`, `components/profile/cheatsheets-panel.tsx:71-90` |
| 14 | P2 | Add the missing intended sections: Learning Recommendations (needs schema fields), a dedicated Potential Concerns card, and Interview Strategy (needs schema fields) | L | `backend/app/schemas/response.py`, new components under `components/` and `components/interviewer/` |
| 15 | P2 | Fix the hydration mismatch: read `localStorage` in an effect (or `useSyncExternalStore`), not in the slice's initial state. Type `useDispatch<AppDispatch>` in `navbar.tsx:23` | S | `redux/slices/authSlice.ts:16-41`, `components/navbar.tsx:23` |
| 16 | P2 | Turn off `ignoreBuildErrors`/`ignoreDuringBuilds` once #6 lands. Pin the `"latest"` deps | S | `next.config.mjs:4-9`, `package.json` |
| 17 | P2 | Wire or remove the Save PDF / Print / Share / feedback buttons. Drop `html2pdf.js` if unused | S | `components/results/candidate.cheatsheet.tsx:31-98`, `components/results/interview-cheatsheet.tsx:35-108` |
| 18 | P2 | Clean up: debug ids and `console.log`s, empty `redux/index.ts`, unused `lib/mock-*.ts`, `next/head` in `layout.tsx`, the `skill-gaps.tsx:102,107` spacing and colour, and NaN-safe distribution in `skills-assessment.tsx:128-168` | S | listed files |
| 19 | P2 | Validate LLM URLs (http/https only, non-empty) before rendering links | S | `components/concept-refresh.tsx:79-87`, `components/interviewer/candidate-overview.tsx:75-113` |
