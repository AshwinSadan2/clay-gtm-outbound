-- 003: the title cascade is now set per campaign by flags, and Blitz Waterfall ICP allows
-- up to 10 tiers, so icp_tier may run 1-10 (was 1-6). A single-title search counts as tier 1.

alter table gtm.contacts drop constraint contacts_icp_tier_check;
alter table gtm.contacts add constraint contacts_icp_tier_check check (icp_tier between 1 and 10);
