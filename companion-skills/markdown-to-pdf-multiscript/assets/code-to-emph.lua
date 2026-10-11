-- Render inline `code` (used in the source markdown to mark German/Greek/Latin
-- terms) as ITALIC instead of typewriter — suits a humanities text and avoids
-- monospace-font glyph gaps for Greek/Cyrillic.
-- NB: keep this as a single pandoc.Str; an earlier word-splitting version
-- corrupted the first Cyrillic letter of multiword terms (produced U+FFFD).
function Code(el)
  return pandoc.Emph({pandoc.Str(el.text)})
end
