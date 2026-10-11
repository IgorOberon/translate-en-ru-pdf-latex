-- structure.lua: structural fixes at the typesetting stage (post-translation).
--
-- 1) OCR front matter: level-1 chapters BEFORE the first real chapter
--    (cover page, publisher page, preface, acknowledgements) become
--    unnumbered; near-empty cover/publisher pages also leave the TOC.
--    Real content chapters then get the numbers the original had.
-- 2) Native heading numbers: when most level-2 headings already carry the
--    original numbering ("## 1 Historical Sketch", "## II Euler's Formula"),
--    LaTeX section numbering is switched off (secnumdepth=0) so the TOC
--    shows the book's own numbers instead of a double "4.2 1 ...".
--    Override with -M heading_numbers=latex.
--
-- Books whose first chapter is real and whose headings carry no native
-- numbers pass through unchanged (strict backwards compatibility).

local stringify = pandoc.utils.stringify

local FM_NAMES = {
  ['Благодарности'] = true, ['Предисловие'] = true, ['Об авторе'] = true,
  ['От автора'] = true, ['Acknowledgements'] = true, ['Acknowledgments'] = true,
  ['Preface'] = true, ['Foreword'] = true, ['About the Author'] = true,
}
local COVER_NAMES = {
  ['Title Page'] = true, ['Copyright'] = true, ['Cover'] = true,
  ['Титульный лист'] = true, ['Титул'] = true, ['Издательские сведения'] = true,
}

local function starts_numbered(txt)
  return txt:match('^%d+[%s.]') ~= nil or txt:match('^[IVXLC]+[%s.]') ~= nil
end

function Pandoc(doc)
  local blocks = doc.blocks
  local chapters = {}
  local cur = nil
  for _, b in ipairs(blocks) do
    if b.t == 'Header' and b.level == 1 then
      cur = { header = b, words = 0, h2 = 0, h2num = 0 }
      chapters[#chapters + 1] = cur
    elseif cur then
      if b.t == 'Header' and b.level == 2 then
        cur.h2 = cur.h2 + 1
        if starts_numbered(stringify(b.content)) then
          cur.h2num = cur.h2num + 1
        end
      elseif b.t == 'Para' or b.t == 'Plain' then
        local _, cnt = stringify(b):gsub('%S+', '')
        cur.words = cur.words + cnt
      end
    end
  end

  -- (1) demote front matter
  for _, c in ipairs(chapters) do
    local name = stringify(c.header.content)
    -- A short chapter is not evidence of front matter. Unknown headings stay
    -- in the ToC, including short books with no numbered subheadings.
    if not FM_NAMES[name] and not COVER_NAMES[name] then
      break
    end
    c.header.classes:insert('unnumbered')
    if c.words < 60 and COVER_NAMES[name] then
      c.header.classes:insert('unlisted')  -- cover/publisher page junk
    end
  end

  -- (2) native heading numbers -> suppress LaTeX section numbers
  local h2, h2num = 0, 0
  for _, c in ipairs(chapters) do
    h2 = h2 + c.h2
    h2num = h2num + c.h2num
  end
  local override = doc.meta.heading_numbers and
      stringify(doc.meta.heading_numbers) or 'auto'
  -- Small documents also carry native numbering; requiring ten headings
  -- produced "1.1. 1 Force" on every short pilot. Require unanimity for these.
  if override ~= 'latex' and ((h2 >= 10 and h2num * 2 >= h2)
                             or (h2 >= 2 and h2num == h2)) then
    table.insert(blocks, 1,
                 pandoc.RawBlock('latex', '\\setcounter{secnumdepth}{0}'))
  end
  return doc
end
