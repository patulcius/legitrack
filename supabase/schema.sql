-- Legitrack : comptes validés par un administrateur, préférences et alertes e-mail.
-- Appliqué sur le projet Supabase « Legitrack » (région eu-west-1). Rejouable sur une base vide.
-- Les adresses des administrateurs ne figurent pas ici : elles sont ajoutées directement en base
-- (insert into public.admins_autorises(email) values ('...')).

-- ------------------------------------------------------------------ tables
create table if not exists public.admins_autorises (
  email text primary key
);

create table if not exists public.profils (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  nom text check (char_length(nom) <= 80),
  statut text not null default 'en_attente' check (statut in ('en_attente', 'valide', 'refuse', 'suspendu')),
  admin boolean not null default false,
  prefs jsonb not null default '{}'::jsonb check (pg_column_size(prefs) < 200000),
  cree_le timestamptz not null default now(),
  valide_le timestamptz,
  valide_par uuid,
  admin_notifie boolean not null default false,       -- l'administrateur a été prévenu de la demande
  validation_notifiee boolean not null default false, -- l'utilisateur a été prévenu de la décision
  quotidien_le date                                    -- date du dernier récapitulatif quotidien
);

create table if not exists public.alertes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.profils(id) on delete cascade,
  cible text not null check (cible in ('mission', 'texte', 'theme', 'tout')),
  cible_id text not null default '' check (char_length(cible_id) <= 120),
  libelle text check (char_length(libelle) <= 400),
  types text[] not null default '{}',                  -- vide = tous les types d'événements
  frequence text not null default 'immediate' check (frequence in ('immediate', 'quotidienne')),
  cree_le timestamptz not null default now(),
  unique (user_id, cible, cible_id)
);
create index if not exists alertes_user_idx on public.alertes(user_id);

create table if not exists public.envois (
  user_id uuid not null references public.profils(id) on delete cascade,
  item_id text not null,
  envoye_le timestamptz not null default now(),
  primary key (user_id, item_id)
);

-- ------------------------------------------------------------------ fonctions d'aide
create or replace function public.est_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profils where id = auth.uid() and admin and statut = 'valide');
$$;

create or replace function public.est_valide() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profils where id = auth.uid() and statut = 'valide');
$$;

-- création du profil à l'inscription (en attente, sauf adresse d'administrateur)
create or replace function public.nouveau_compte() returns trigger
language plpgsql security definer set search_path = '' as $$
declare est_adm boolean;
begin
  select exists (select 1 from public.admins_autorises a where lower(a.email) = lower(new.email)) into est_adm;
  insert into public.profils (id, email, nom, statut, admin, valide_le, admin_notifie, validation_notifiee)
  values (new.id, new.email, left(nullif(trim(new.raw_user_meta_data->>'nom'), ''), 80),
          case when est_adm then 'valide' else 'en_attente' end, est_adm,
          case when est_adm then now() end, est_adm, est_adm)
  on conflict (id) do nothing;
  return new;
end $$;

create or replace function public.maj_email() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.profils set email = new.email where id = new.id;
  return new;
end $$;

drop trigger if exists legitrack_nouveau_compte on auth.users;
create trigger legitrack_nouveau_compte after insert on auth.users
  for each row execute function public.nouveau_compte();
drop trigger if exists legitrack_maj_email on auth.users;
create trigger legitrack_maj_email after update of email on auth.users
  for each row when (old.email is distinct from new.email) execute function public.maj_email();

-- ------------------------------------------------------------------ actions d'administration
create or replace function public.admin_statut(cible uuid, nouveau text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not public.est_admin() then raise exception 'Réservé aux administrateurs'; end if;
  if cible = auth.uid() then raise exception 'Impossible de modifier son propre compte'; end if;
  if nouveau not in ('valide', 'refuse', 'suspendu', 'en_attente') then raise exception 'Statut inconnu'; end if;
  update public.profils
     set statut = nouveau, valide_le = now(), valide_par = auth.uid(),
         validation_notifiee = (nouveau in ('suspendu', 'en_attente'))  -- prévenir en cas de validation ou de refus
   where id = cible;
end $$;

create or replace function public.admin_role(cible uuid, est boolean) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not public.est_admin() then raise exception 'Réservé aux administrateurs'; end if;
  if cible = auth.uid() then raise exception 'Impossible de modifier son propre compte'; end if;
  update public.profils set admin = est where id = cible and statut = 'valide';
end $$;

create or replace function public.admin_supprimer(cible uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not public.est_admin() then raise exception 'Réservé aux administrateurs'; end if;
  if cible = auth.uid() then raise exception 'Utilisez « Supprimer mon compte »'; end if;
  delete from auth.users where id = cible;
end $$;

-- droit à l'effacement (RGPD) : supprime le compte, les préférences, les alertes et l'historique d'envoi
create or replace function public.supprimer_mon_compte() returns void
language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then raise exception 'Non connecté'; end if;
  delete from auth.users where id = auth.uid();
end $$;

-- ------------------------------------------------------------------ droits et RLS
alter table public.admins_autorises enable row level security;
alter table public.profils enable row level security;
alter table public.alertes enable row level security;
alter table public.envois enable row level security;

revoke all on public.admins_autorises, public.profils, public.alertes, public.envois from anon, authenticated;
grant select on public.profils to authenticated;
grant update (nom, prefs) on public.profils to authenticated;
grant select, insert, update, delete on public.alertes to authenticated;

drop policy if exists profils_lecture on public.profils;
create policy profils_lecture on public.profils for select to authenticated
  using (id = (select auth.uid()) or (select public.est_admin()));
drop policy if exists profils_maj on public.profils;
create policy profils_maj on public.profils for update to authenticated
  using (id = (select auth.uid()) and (select public.est_valide()))
  with check (id = (select auth.uid()));

drop policy if exists alertes_perso on public.alertes;
create policy alertes_perso on public.alertes for all to authenticated
  using (user_id = (select auth.uid()) and (select public.est_valide()))
  with check (user_id = (select auth.uid()) and (select public.est_valide()));

revoke execute on function public.est_admin(), public.est_valide(), public.nouveau_compte(), public.maj_email(),
  public.admin_statut(uuid, text), public.admin_role(uuid, boolean), public.admin_supprimer(uuid),
  public.supprimer_mon_compte() from public, anon;
grant execute on function public.est_admin(), public.est_valide(), public.admin_statut(uuid, text),
  public.admin_role(uuid, boolean), public.admin_supprimer(uuid), public.supprimer_mon_compte() to authenticated;
