CREATE DATABASE IF NOT EXISTS softeng25_17;
USE softeng25_17;


CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    has_subscription BOOLEAN,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE subscriptions (
    subscription_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    subscription_status VARCHAR(100),
    started_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE points (
    point_id INT PRIMARY KEY,
    provider_name VARCHAR (100),
    lon DECIMAL(7, 4),
    lat DECIMAL(7, 4),
    status ENUM('available','charging','reserved','malfunction','offline') NOT NULL,
    cap INT,
    reservation_end_time TIMESTAMP,
    kwh_price FLOAT,
    state_or_province VARCHAR(100),
    holder_username VARCHAR(100)
);

CREATE TABLE sessions (
    session_id INT AUTO_INCREMENT PRIMARY KEY,
    point_id INT NOT NULL,
    user_id INT NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NULL,
    start_soc INT NOT NULL,
    end_soc INT NULL,
    total_kwh FLOAT NULL,
    session_kwh_price FLOAT NOT NULL,
    amount FLOAT NULL,
    state ENUM('active', 'completed', 'pending') DEFAULT 'active',
    FOREIGN KEY (point_id) REFERENCES points(point_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE point_changes (
    point_changes_id INT AUTO_INCREMENT PRIMARY KEY,
    point_id INT,
    timeref TIMESTAMP,
    old_state VARCHAR(100),
    new_state VARCHAR(100),

    CONSTRAINT fk_ps_point 
        FOREIGN KEY (point_id) REFERENCES points(point_id) 
        ON DELETE CASCADE
);

DELIMITER $$

CREATE TRIGGER point_update
AFTER UPDATE ON points
FOR EACH ROW
BEGIN

    DECLARE timeref TIMESTAMP;
    DECLARE old_state VARCHAR(100);
    DECLARE new_state VARCHAR(100);

    IF OLD.point_id = NEW.point_id AND OLD.status <> NEW.status THEN

        SELECT CURRENT_TIMESTAMP INTO timeref;
        SELECT OLD.status INTO old_state;
        SELECT NEW.status INTO new_state;

        INSERT INTO point_changes (point_id, timeref, old_state, new_state)
	VALUES (NEW.point_id, timeref, old_state, new_state);
    END IF;

END$$

DELIMITER ;
