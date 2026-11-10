-- Restrict direct RPC execution of the automatic RLS event-trigger function.
-- The event trigger remains enabled; PostgreSQL fires it through the event-trigger
-- catalog and this function continues to run with its SECURITY DEFINER owner context.
-- This migration only removes unnecessary direct EXECUTE grants from API roles.
REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM anon, authenticated;
