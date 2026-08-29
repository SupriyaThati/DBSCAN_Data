-- ============================================================
-- Run this against BOTH your old (source) and new (target)
-- MySQL servers before switching config.py's DEMO_MODE to False.
--
--   mysql -u root -p old_company_db < schema.sql
--   mysql -u root -p new_company_db < schema.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS customers (
    id       INT PRIMARY KEY AUTO_INCREMENT,
    name     VARCHAR(255),
    phone    VARCHAR(20),
    email    VARCHAR(255)
);

-- Optional: a few messy rows to test the duplicate detector against
-- real MySQL once DEMO_MODE = False (only insert these into the
-- SOURCE / old database, not the target).
--
-- INSERT INTO customers (name, phone, email) VALUES
--   ('Rahul Kumar',  '9876543210', 'rahul@gmail.com'),
--   ('Rahul  Kumar', '9876543210', 'rahul@gmail.com'),
--   ('R. Kumar',     '9876543210', 'rahul@gmail.com');
