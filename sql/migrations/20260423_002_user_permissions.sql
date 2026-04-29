ALTER TABLE finvue_users
  ADD COLUMN permissions JSON NULL AFTER role;
