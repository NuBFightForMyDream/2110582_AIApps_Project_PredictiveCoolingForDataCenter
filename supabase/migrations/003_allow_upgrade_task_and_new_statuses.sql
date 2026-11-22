-- Allow cases from the "Plan upgrades" task (Hardware Engineer, skill S8). Run after 001 and 002.
-- The new statuses (security_alert) and decisions (upgrade_plan) need no change: those columns are free text.
alter table agent_cases drop constraint if exists agent_cases_task_check;
alter table agent_cases add constraint agent_cases_task_check
  check (task in ('recommend', 'analyze', 'upgrade'));
