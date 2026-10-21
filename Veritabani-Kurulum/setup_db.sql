-- Mail Kontrol Sistemi - Veritabanı Kurulum Script
-- Tarih: 2026-06-23

CREATE DATABASE IF NOT EXISTS mail_kontrol CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE mail_kontrol;

-- Kullanıcılar tablosu
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ad VARCHAR(100) DEFAULT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  sifre VARCHAR(255) NOT NULL,
  gmail_hesabi VARCHAR(255) DEFAULT NULL,
  gmail_sifre VARCHAR(255) DEFAULT NULL,
  analiz_idx INT DEFAULT 0,
  son_imap_toplam INT DEFAULT 0,
  tarih VARCHAR(20) DEFAULT NULL,
  CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Önemli Mailler
CREATE TABLE IF NOT EXISTS mails_onemli (
  id INT AUTO_INCREMENT PRIMARY KEY,
  message_id VARCHAR(512) DEFAULT NULL,
  gonderen VARCHAR(512) DEFAULT NULL,
  konu TEXT DEFAULT NULL,
  tarih VARCHAR(20) DEFAULT NULL,
  user_id INT NOT NULL DEFAULT 1,
  UNIQUE KEY uid_mid (message_id, user_id),
  KEY user_idx (user_id),
  CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Önemsiz Mailler
CREATE TABLE IF NOT EXISTS mails_onemsiz (
  id INT AUTO_INCREMENT PRIMARY KEY,
  message_id VARCHAR(512) DEFAULT NULL,
  gonderen VARCHAR(512) DEFAULT NULL,
  konu TEXT DEFAULT NULL,
  tarih VARCHAR(20) DEFAULT NULL,
  user_id INT NOT NULL DEFAULT 1,
  UNIQUE KEY uid_mid (message_id, user_id),
  KEY user_idx (user_id),
  CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Spam Mailler
CREATE TABLE IF NOT EXISTS mails_spam (
  id INT AUTO_INCREMENT PRIMARY KEY,
  message_id VARCHAR(512) DEFAULT NULL,
  gonderen VARCHAR(512) DEFAULT NULL,
  konu TEXT DEFAULT NULL,
  tarih VARCHAR(20) DEFAULT NULL,
  user_id INT NOT NULL DEFAULT 1,
  UNIQUE KEY uid_mid (message_id, user_id),
  KEY user_idx (user_id),
  CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Kullanıcı Düzeltmeleri (Few-shot örnekleri)
CREATE TABLE IF NOT EXISTS duzeltmeler (
  id INT AUTO_INCREMENT PRIMARY KEY,
  gonderen VARCHAR(255) DEFAULT NULL,
  konu TEXT DEFAULT NULL,
  eski_karar VARCHAR(20) DEFAULT NULL,
  yeni_karar VARCHAR(20) DEFAULT NULL,
  tarih VARCHAR(20) DEFAULT NULL,
  user_id INT NOT NULL,
  KEY user_idx (user_id),
  CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Kullanıcı Kuralları
CREATE TABLE IF NOT EXISTS kurallar (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tur VARCHAR(20) NOT NULL,
  deger VARCHAR(512) NOT NULL,
  karar VARCHAR(20) NOT NULL,
  tarih VARCHAR(20) DEFAULT NULL,
  user_id INT NOT NULL DEFAULT 1,
  KEY user_idx (user_id),
  CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- İndeksler - Hız için
ALTER TABLE mails_onemli ADD INDEX idx_user_tarih (user_id, tarih);
ALTER TABLE mails_onemsiz ADD INDEX idx_user_tarih (user_id, tarih);
ALTER TABLE mails_spam ADD INDEX idx_user_tarih (user_id, tarih);

COMMIT;
