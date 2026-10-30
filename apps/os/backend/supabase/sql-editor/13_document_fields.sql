-- SQL editor paste 13 of 15: 0014_document_fields.sql
-- Paste all of this into the Supabase SQL editor and press Run.
-- Wait for "Success" before you paste the next file.

-- =============================================================================
-- 0014  Content: which fields are documents (see 0013)
--
-- The fields below open in the app's editor and in the AI connector's docs.*
-- actions. board = the card table; empty = the client page. The *_url column
-- stays: it is the "paste a link instead".
--
-- videos.caption is gone: its text is now the "caption" document of each card.
-- Any text already in it is moved into a document first.
-- Safe to run twice.
-- =============================================================================

insert into public.document_fields (board, field_key, label, link_column) values
  ('videos', 'caption', 'Caption', null),
  (null, 'strategy_brief', 'Strategy brief', 'strategy_brief_url')
on conflict on constraint document_fields_key do update
  set label = excluded.label, link_column = excluded.link_column;

do $move$
begin
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'videos' and column_name = 'caption') then
    insert into public.documents (client_id, board, card_id, field_key, body_md, word_count)
    select c.client_id, 'videos', c.id, 'caption', c.caption,
           coalesce(array_length(regexp_split_to_array(btrim(c.caption), '\s+'), 1), 0)
    from public.videos c
    where btrim(coalesce(c.caption, '')) <> ''
    on conflict on constraint documents_key do nothing;
    alter table public.videos drop column caption;
  end if;
end
$move$;
