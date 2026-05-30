CREATE DATABASE IF NOT EXISTS culture_video_agent
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE culture_video_agent;

CREATE TABLE IF NOT EXISTS videos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  video_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(500) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS calligraphy_glyphs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  `character` VARCHAR(16) NOT NULL,
  style VARCHAR(64) NOT NULL,
  author VARCHAR(64) NOT NULL,
  image_path VARCHAR(500) NOT NULL,
  width INT NULL,
  height INT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_calligraphy_lookup (`character`, style, author),
  INDEX idx_calligraphy_style_author (style, author)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO videos (video_name, file_path) VALUES
('兰花花.mp4', '/data/culture-agent/media/video/兰花花.mp4'),
('信天游介绍.mp4', '/data/culture-agent/media/video/信天游介绍.mp4'),
('走西口.mp4', '/data/culture-agent/media/video/走西口.mp4'),
('赶牲灵.mp4', '/data/culture-agent/media/video/赶牲灵.mp4'),
('山丹丹开花红艳艳.mp4', '/data/culture-agent/media/video/山丹丹开花红艳艳.mp4'),
('三十里铺.mp4', '/data/culture-agent/media/video/三十里铺.mp4'),
('东方红.mp4', '/data/culture-agent/media/video/东方红.mp4');
