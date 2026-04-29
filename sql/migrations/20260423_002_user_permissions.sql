ALTER TABLE users
  ADD COLUMN permissions JSON NULL AFTER role;
