-- Legitrack : agenda Outlook personnel (24/11/2026). À exécuter une fois dans l'éditeur SQL de Supabase.
-- Chaque compte reçoit une adresse d'agenda non devinable, ics/u/<jeton>.ics, régénérée à chaque collecte
-- par scripts/agendas_perso.py à partir des textes et missions suivis.
alter table public.profils add column if not exists agenda_jeton uuid not null default gen_random_uuid();
create unique index if not exists profils_agenda_jeton_idx on public.profils(agenda_jeton);

-- changer d'adresse (l'ancienne cesse de fonctionner à la collecte suivante)
create or replace function public.nouveau_jeton_agenda() returns uuid
language plpgsql security definer set search_path = public as $$
declare j uuid := gen_random_uuid();
begin
  if not public.est_valide() then raise exception 'compte non validé'; end if;
  update public.profils set agenda_jeton = j where id = auth.uid();
  return j;
end $$;
revoke execute on function public.nouveau_jeton_agenda() from public, anon;
grant execute on function public.nouveau_jeton_agenda() to authenticated;
