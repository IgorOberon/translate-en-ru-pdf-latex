# Конспект format (from a seminar transcript)

A конспект is a topic-structured summary of the meeting, **not** a chronological retelling. Read
the *whole* transcript first, group what was said into themes and decisions, then write. The ASR is
rough in places — synthesize meaning, don't quote garbled fragments.

## Hard conventions (project rules)

- **No names. Roles only.** This project deliberately anonymizes: use «докладчик / разработчик
  пособия», «автор мини-лекции», «методисты и организаторы». Even though the transcript contains
  names, never put them in the конспект.
- **Timecodes on substantive points** via a small macro (`\tc{00:43}`), so a reader can jump back to
  the audio. Pull them straight from the `**[hh:mm:ss]**` markers.
- **Hidden framework stays hidden.** Per the project's незыблемые правила, do not mention Hegel /
  categories anywhere — operational language only.
- Build with **lualatex** (not latexmk; Perl isn't installed), 2 passes. Fonts: STIX Two + DejaVu
  via `nppstyle.sty` (copy it into the konspekt's folder). Verify `pdffonts` → 0 Type3.

## Skeleton (matches the existing `notes/` and `notes2/` конспекты)

```latex
\documentclass[11pt]{article}
\usepackage{nppstyle}
\pagestyle{fancy}\fancyhf{}\renewcommand{\headrulewidth}{0.3pt}
\fancyhead[L]{\footnotesize\headingfont\color{softgray}Конспект семинара}
\fancyhead[R]{\footnotesize\headingfont\color{softgray}<ДД.ММ.ГГГГ>}
\fancyfoot[C]{\footnotesize\headingfont\color{softgray}\thepage}
\newcommand{\tc}[1]{{\headingfont\bfseries\footnotesize\color{accent}[#1]}~}  % таймкод

\begin{document}\frenchspacing
\begin{center}
{\headingfont\bfseries\color{inkblue}\LARGE Конспект рабочего семинара\par}\vspace{2mm}
{\headingfont\color{accent}\large <подзаголовок>\par}\vspace{1mm}
{\color{softgray} <дата>}
\end{center}\vspace{2mm}

\begin{defbox}[О встрече]\setlength{\parindent}{0pt}
\textbf{Формат.} … \\[2pt]\textbf{Цель.} … \\[2pt]
\textbf{Участники (роли, без имён).} … \\[2pt]\textbf{Главный итог.} …
\end{defbox}

\begin{notebox}[Связь с пособием]…\end{notebox}

\section{<Тема>}
\begin{itemize}
  \item \tc{00:02} \textbf{Короткий тезис.} Пояснение.
  …
\end{itemize}
% … разделы по темам …

\section{Организационные решения и следующие шаги}
\begin{keybox}[Договорённости]\setlength{\parindent}{0pt}
\begin{itemize}[leftmargin=1.4em] … \end{itemize}
\end{keybox}

\section*{Открытые вопросы}\addcontentsline{toc}{section}{Открытые вопросы}
\begin{notebox}[Что осталось продумать]\begin{itemize}[leftmargin=1.4em] … \end{itemize}\end{notebox}
\end{document}
```

## Box environments available in `nppstyle.sty`
`defbox` (определение/о встрече), `notebox` (замечание/связь), `keybox` (главное/договорённости),
`exbox` (пример), `deepbox` (под капотом). Each takes an optional `[title]`.

## Build & QA
```powershell
cd "<folder>"; lualatex --interaction=nonstopmode <file>.tex; lualatex --interaction=nonstopmode <file>.tex
pdffonts <file>.pdf | Select-String "Type 3"   # must be empty
```
Then copy the PDF to `output/` with a friendly Russian name, and add a row to both `README.md` and
`PROJECT_STATE.md`. Watch the usual traps: keep math out of section titles (breaks bookmarks); write
literal arrows as `$\to$`; Cyrillic only through STIX Two / DejaVu.

## Sectioning hints
Typical buckets that recur in these planning seminars: замысел/цели, формат курса (уроки, уровни,
модули), поурочная раскладка по модулям, банк практики/лабораторных, связь с олимпиадой,
инструменты/железо, оргрешения и следующие шаги, открытые вопросы. Use whatever themes the actual
meeting produced — these are just a starting palette.
