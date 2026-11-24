-- Legitrack : lancement fiable des mises à jour (24/11/2026).
-- GitHub retarde ou abandonne souvent ses tâches programmées (« schedule »). Ici, Supabase lance
-- lui-même le workflow aux heures prévues, comme un lancement manuel (workflow_dispatch).
--
-- Prérequis, une seule fois :
--  1. Créer sur GitHub un jeton « fine-grained » limité au dépôt patulcius/legitrack,
--     avec la seule permission « Actions : Read and write ».
--  2. Dans Supabase : Project Settings > Vault > « Add new secret », nom : github_legitrack,
--     valeur : le jeton. Il ne doit jamais apparaître dans le dépôt.
--  3. Exécuter ce fichier dans SQL Editor.
-- Les heures sont en UTC, comme dans .github/workflows/update.yml (8 h 30 et 14 h à Paris en hiver).

create extension if not exists pg_cron;
create extension if not exists pg_net;

create or replace function public.lancer_maj(mode text) returns bigint
language plpgsql security definer set search_path = public as $$
declare jeton text;
begin
  select decrypted_secret into jeton from vault.decrypted_secrets where name = 'github_legitrack';
  if jeton is null then raise notice 'secret github_legitrack absent du coffre-fort'; return null; end if;
  return net.http_post(
    url := 'https://api.github.com/repos/patulcius/legitrack/actions/workflows/update.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || jeton,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'legitrack-supabase'),
    body := jsonb_build_object('ref', 'main', 'inputs', jsonb_build_object('mode', mode)));
end $$;
revoke execute on function public.lancer_maj(text) from public, anon, authenticated;

select cron.schedule('legitrack-complete-matin', '30 7 * * *',    $$select public.lancer_maj('full')$$);
select cron.schedule('legitrack-complete-aprem', '0 13 * * *',    $$select public.lancer_maj('full')$$);
select cron.schedule('legitrack-legere',         '5 6-20 * * 1-5', $$select public.lancer_maj('light')$$);

-- Vérifier : select * from cron.job;
-- Derniers appels (201/204 = accepté) : select status_code, content from net._http_response order by created desc limit 5;
-- Tester tout de suite : select public.lancer_maj('light');
