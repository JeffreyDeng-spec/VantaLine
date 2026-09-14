# VantaLine batch label inspection

**Status: Authoritative**

Explicitly enable $vantaline-label-inspection. First read
/work/.agents/skills/vantaline-label-inspection/SKILL.md and its batch CLI reference.
This is label-batch-v3, one whole order batch in ONE session, with a shared 600-second
wall deadline. Read /input/batch.json and `vantaline batch show`.
Do not start other sessions, agents, OCR or external model services.
Publish a match outcome for EVERY actual label before detailed inspections.
Inspect frozen full images, using /input/index-*.jpg only for navigation.
All standard normalized PNGs are /input/media/{media.image}.png.
Use --label LABEL_ID for every label-scoped command, including crop/decode/evidence.
Publish elements and a checklist early for all confidently matched labels. Then
check progressively, prioritizing suspicious regions without dropping other labels.
Unmatched/ambiguous actuals MUST be needs_confirmation, never ignored or falsely
claimed missing from the document. Unused document images are outside the scope.
Leave genuinely uninspected checks pending when time expires; never finalize a
partial batch as completed. Record a provisional batch summary if time is short.
Write Chinese user-facing findings and preserve original inspected text verbatim.
