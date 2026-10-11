-- figcaption.lua: bind a figure image to its caption paragraph.
--
-- Handles the two shapes the OCR markdown produces:
--   (a) one Para: [Image, LineBreak, "Рисунок [N] ..."]   (hard break)
--   (b) Para [Image] followed by a Para starting with the caption words
-- and rewrites them to \FigWithCaption{<path>}{<caption latex>} — a
-- centered image with a \small caption whose width follows the image
-- (defined in the preamble next to the \FigMeasureBox auto-fit wrapper).
-- LaTeX auto-numbering stays off: the numbers already live in the captions.

local function starts_caption(inlines)
  local s = pandoc.utils.stringify(inlines)
  return s:find('Рисунок [', 1, true) == 1
      or s:find('Рис.', 1, true) == 1
      or s:find('Figure [', 1, true) == 1
      or s:match('^Рисунок%s+%d') ~= nil
      or s:match('^Figure%s+%d') ~= nil
      or s:match('^Fig%.%s*%d') ~= nil
end

local function latex_of_inlines(inls)
  local doc = pandoc.Pandoc({ pandoc.Plain(inls) })
  return pandoc.write(doc, 'latex'):gsub('%s+$', '')
end

local function fig_block(src, cap_inlines)
  return pandoc.RawBlock('latex', string.format(
    '\\FigWithCaption{%s}{%s}', src, latex_of_inlines(cap_inlines)))
end

function Blocks(blocks)
  local out = pandoc.Blocks({})
  local i = 1
  while i <= #blocks do
    local b, nxt = blocks[i], blocks[i + 1]
    local handled = false
    -- (a) image + hard break + caption inside one paragraph
    if b.t == 'Para' and #b.content >= 3
        and b.content[1].t == 'Image' and b.content[2].t == 'LineBreak' then
      local cap = pandoc.List({})
      for j = 3, #b.content do cap:insert(b.content[j]) end
      if starts_caption(cap) then
        out:insert(fig_block(b.content[1].src, cap))
        handled = true
        i = i + 1
      end
    end
    -- (b) lone image paragraph + separate caption paragraph
    if not handled and b.t == 'Para' and #b.content == 1
        and b.content[1].t == 'Image'
        and nxt and nxt.t == 'Para' and starts_caption(nxt.content) then
      out:insert(fig_block(b.content[1].src, nxt.content))
      handled = true
      i = i + 2
    end
    if not handled then
      out:insert(b)
      i = i + 1
    end
  end
  return out
end
