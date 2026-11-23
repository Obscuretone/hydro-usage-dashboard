-- Apply to a dedicated database. Do not reuse another application's schema.
CREATE TABLE IF NOT EXISTS hours (
    contract VARCHAR(255) NOT NULL,
    timestamp VARCHAR(60) NOT NULL,
    kwh DOUBLE,
    temperature_c DOUBLE,
    quality LONGTEXT,
    PRIMARY KEY (contract, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_nopad_bin;
CREATE TABLE IF NOT EXISTS metadata (
    contract VARCHAR(255) NOT NULL PRIMARY KEY,
    payload LONGTEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_nopad_bin;
