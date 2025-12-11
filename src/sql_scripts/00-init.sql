-- =========================
-- 00-init.sql
-- Create DB + Stage tables + Normalized schema + Seed
-- =========================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

CREATE DATABASE IF NOT EXISTS curriculum_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE curriculum_db;

-- =====================================================
-- STAGE TABLES (raw/denormalized import)
-- =====================================================

-- 1) information
CREATE TABLE IF NOT EXISTS information (
  curriculum TEXT,
  docx_id TEXT,
  pdf_id TEXT,

  finish_info INT,
  finish_course INT,
  curr_id INT,

  faculty TEXT,
  curr_name_th TEXT,
  curr_name_en TEXT,

  degree_full_th TEXT,
  degree_full_en TEXT,
  degree_abr_th TEXT,
  degree_abr_en TEXT,

  campus TEXT,
  curr_category TEXT,
  curr_type TEXT,
  lang TEXT,
  mou TEXT,

  first_open_semester INT,
  first_open_year INT,

  careers TEXT,
  expense_type TEXT,
  student_nation TEXT,
  qualification_collegian TEXT,

  max_semester INT,
  day_class TEXT,
  type_class TEXT,

  total_credits INT,
  gen_ed_credits INT,
  spec_credits INT,
  elec_credits INT,
  free_elec_credits INT,

  count_research INT,
  count_academic_paper INT,
  count_lecturer_academic INT,
  count_lecturer_full INT,
  count_lecturer_extra INT,
  count_staff INT,

  other_grade TEXT,
  criteria_graduate TEXT,
  curr_qa TEXT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- 2) plo
CREATE TABLE IF NOT EXISTS plo (
  curriculum TEXT,
  type_plo TEXT,
  num_plo INT,
  detail_plo TEXT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- 3) qualification_responsible
CREATE TABLE IF NOT EXISTS qualification_responsible (
  curriculum TEXT,
  qualification_responsible_position TEXT,
  name_responsible TEXT,
  degree_reponsible TEXT,
  program_responsible TEXT,
  institute_responsible TEXT,
  year_graduate_responsible INT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- 4) course
CREATE TABLE IF NOT EXISTS course (
  curriculum TEXT,
  course_type TEXT,

  th_abv TEXT,
  th_name TEXT,
  eng_abv TEXT,
  eng_name TEXT,

  credit INT,
  lect_hours INT,
  practice_hours INT,
  self_hours INT,

  th_desc TEXT,
  eng_desc TEXT,
  prerequisite TEXT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


-- =====================================================
-- LOOKUP TABLES
-- =====================================================

CREATE TABLE IF NOT EXISTS curr_category (
  curr_category_id INT AUTO_INCREMENT PRIMARY KEY,
  curr_category TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS expense_type (
  expense_type_id INT AUTO_INCREMENT PRIMARY KEY,
  expense_type TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS curr_type_details (
  curr_type_id INT AUTO_INCREMENT PRIMARY KEY,
  curr_type TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS student_nation (
  student_nation_id INT AUTO_INCREMENT PRIMARY KEY,
  student_nation TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS campus (
  campus_id INT AUTO_INCREMENT PRIMARY KEY,
  campus TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS curr_languages (
  lang_id INT AUTO_INCREMENT PRIMARY KEY,
  lang TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS mou (
  mou_id INT AUTO_INCREMENT PRIMARY KEY,
  mou TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS day_class (
  day_class_id INT AUTO_INCREMENT PRIMARY KEY,
  day_class TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS type_class (
  type_class_id INT AUTO_INCREMENT PRIMARY KEY,
  type_class TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- =====================================================
-- MAIN TABLE: curriculum
-- PK = curr_name_th_id (AUTO_INCREMENT)
-- bigint -> int already applied
-- =====================================================

CREATE TABLE IF NOT EXISTS curriculum (
  curr_id INT,
  faculty TEXT,

  curr_name_th_id INT AUTO_INCREMENT PRIMARY KEY,

  curr_name_en TEXT,

  degree_full_th TEXT,
  degree_full_en TEXT,
  degree_abr_th TEXT,
  degree_abr_en TEXT,

  campus_id INT,
  curr_category_id INT,
  curr_type_id INT,
  lang_id INT,
  mou_id INT,

  first_open_semester INT,
  first_open_year INT,
  careers TEXT,

  expense_type_id INT,
  student_nation_id INT,
  qualification_collegian TEXT,

  max_semester INT,
  day_class_id INT,
  type_class_id INT,

  total_credits INT,
  gen_ed_credits INT,
  spec_credits INT,
  elec_credits INT,
  free_elec_credits INT,

  count_research INT,
  count_academic_paper INT,
  count_lecturer_academic INT,
  count_lecturer_full INT,
  count_lecturer_extra INT,
  count_lecturer_staff INT,

  other_grade TEXT,
  criteria_graduate TEXT,

  INDEX idx_curr_campus (campus_id),
  INDEX idx_curr_category (curr_category_id),
  INDEX idx_curr_type (curr_type_id),
  INDEX idx_curr_lang (lang_id),
  INDEX idx_curr_mou (mou_id),
  INDEX idx_curr_expense (expense_type_id),
  INDEX idx_curr_nation (student_nation_id),
  INDEX idx_curr_day_class (day_class_id),
  INDEX idx_curr_type_class (type_class_id),

  CONSTRAINT fk_curr_campus
    FOREIGN KEY (campus_id) REFERENCES campus(campus_id)
    ON UPDATE CASCADE ON DELETE SET NULL,

  CONSTRAINT fk_curr_category
    FOREIGN KEY (curr_category_id) REFERENCES curr_category(curr_category_id)
    ON UPDATE CASCADE ON DELETE SET NULL,

  CONSTRAINT fk_curr_type
    FOREIGN KEY (curr_type_id) REFERENCES curr_type_details(curr_type_id)
    ON UPDATE CASCADE ON DELETE SET NULL,

  CONSTRAINT fk_curr_lang
    FOREIGN KEY (lang_id) REFERENCES curr_languages(lang_id)
    ON UPDATE CASCADE ON DELETE SET NULL,

  CONSTRAINT fk_curr_mou
    FOREIGN KEY (mou_id) REFERENCES mou(mou_id)
    ON UPDATE CASCADE ON DELETE SET NULL,

  CONSTRAINT fk_curr_expense
    FOREIGN KEY (expense_type_id) REFERENCES expense_type(expense_type_id)
    ON UPDATE CASCADE ON DELETE SET NULL,

  CONSTRAINT fk_curr_nation
    FOREIGN KEY (student_nation_id) REFERENCES student_nation(student_nation_id)
    ON UPDATE CASCADE ON DELETE SET NULL,

  CONSTRAINT fk_curr_day_class
    FOREIGN KEY (day_class_id) REFERENCES day_class(day_class_id)
    ON UPDATE CASCADE ON DELETE SET NULL,

  CONSTRAINT fk_curr_type_class
    FOREIGN KEY (type_class_id) REFERENCES type_class(type_class_id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- =====================================================
-- 1:1 normalized name table
-- =====================================================

CREATE TABLE IF NOT EXISTS curr_name_th (
  curr_name_th_id INT PRIMARY KEY,
  curr_name_th TEXT,

  CONSTRAINT fk_curr_name_th_curriculum
    FOREIGN KEY (curr_name_th_id)
    REFERENCES curriculum(curr_name_th_id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- =====================================================
-- Responsible lectures
-- =====================================================

CREATE TABLE IF NOT EXISTS responsible_lectures_background (
  responsible_id INT AUTO_INCREMENT PRIMARY KEY,
  name_responsible TEXT,
  qualification_responsible_position TEXT,
  degree_reponsible TEXT,
  program_responsible TEXT,
  institute_responsible TEXT,
  year_graduate_responsible INT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS responsible_lectures (
  curr_name_th_id INT,
  responsible_id INT,

  PRIMARY KEY (curr_name_th_id, responsible_id),

  CONSTRAINT fk_resp_lect_curr
    FOREIGN KEY (curr_name_th_id)
    REFERENCES curriculum(curr_name_th_id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,

  CONSTRAINT fk_resp_lect_bg
    FOREIGN KEY (responsible_id)
    REFERENCES responsible_lectures_background(responsible_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- =====================================================
-- Courses (normalized)
-- =====================================================

CREATE TABLE IF NOT EXISTS course_detail (
  course_id INT AUTO_INCREMENT PRIMARY KEY,

  th_abv VARCHAR(10),
  eng_abv VARCHAR(10),
  th_name TEXT,
  eng_name TEXT,

  credit DECIMAL(4,1),
  lect_hours INT,
  practice_hours INT,
  self_hours INT,

  th_desc TEXT,
  eng_desc TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS course_type (
  course_type_id INT AUTO_INCREMENT PRIMARY KEY,
  course_type TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS courses (
  curr_name_th_id INT,
  course_id INT,
  course_type_id INT,
  prerequisite VARCHAR(100),

  PRIMARY KEY (curr_name_th_id, course_id),
  INDEX idx_courses_type (course_type_id),

  CONSTRAINT fk_courses_curr
    FOREIGN KEY (curr_name_th_id)
    REFERENCES curriculum(curr_name_th_id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,

  CONSTRAINT fk_courses_detail
    FOREIGN KEY (course_id)
    REFERENCES course_detail(course_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,

  CONSTRAINT fk_courses_type
    FOREIGN KEY (course_type_id)
    REFERENCES course_type(course_type_id)
    ON UPDATE CASCADE
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- =====================================================
-- PLOs / Learning outcomes (normalized)
-- =====================================================

CREATE TABLE IF NOT EXISTS plos_type (
  plos_type_id INT AUTO_INCREMENT PRIMARY KEY,
  plos_num INT,
  plos_type TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS learning_outcome (
  curr_name_th_id INT,
  plos_type_id INT,
  plos_detail TEXT,

  PRIMARY KEY (curr_name_th_id, plos_type_id),

  CONSTRAINT fk_lo_curr
    FOREIGN KEY (curr_name_th_id)
    REFERENCES curriculum(curr_name_th_id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,

  CONSTRAINT fk_lo_plos_type
    FOREIGN KEY (plos_type_id)
    REFERENCES plos_type(plos_type_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- =====================================================
-- QA (normalized)
-- =====================================================

CREATE TABLE IF NOT EXISTS curr_qa_type (
  curr_qa_id INT AUTO_INCREMENT PRIMARY KEY,
  curr_qa_name TEXT,
  curr_qa_type TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS curr_qa (
  curr_name_th_id INT,
  curr_qa_id INT,

  PRIMARY KEY (curr_name_th_id, curr_qa_id),

  CONSTRAINT fk_curr_qa_curr
    FOREIGN KEY (curr_name_th_id)
    REFERENCES curriculum(curr_name_th_id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,

  CONSTRAINT fk_curr_qa_type
    FOREIGN KEY (curr_qa_id)
    REFERENCES curr_qa_type(curr_qa_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- =====================================================
-- Seed data: curr_qa_type
-- =====================================================

INSERT INTO curr_qa_type (curr_qa_name, curr_qa_type)
VALUES
  ('AACSB', 'สากล'),
  ('EQUIS', 'สากล'),
  ('AMBA', 'สากล'),
  ('AUN-QA', 'สากล'),
  ('EQANIE', 'สากล'),
  ('UNWTO.TedQual', 'สากล'),
  ('WFME', 'สากล'),
  ('EdPEx', 'ภายใน'),
  ('IQA', 'ภายใน'),
  ('สป.อว.', 'ภายใน'),
  ('CHEQAOnline', 'ภายใน'),
  ('TQF', 'ภายใน'),
  ('GREATS', 'ภายใน'),
  ('สภาการพยาบาล', 'วิชาชีพ'),
  ('เกณฑ์สภาวิชาชีพกายภาพบำบัด', 'วิชาชีพ'),
  ('แพทยสภา', 'วิชาชีพ'),
  ('มาตรฐานของสภาเทคนิคการแพทย์', 'วิชาชีพ'),
  ('สภาการแพทย์แผนไทย(สภาวิชาชีพ)', 'วิชาชีพ'),
  ('TABEE', 'วิชาชีพ'),
  ('HA', 'วิชาชีพ'),
  ('IMEAc', 'วิชาชีพ');

LOAD DATA LOCAL INFILE '/docker-entrypoint-initdb.d/information.csv'
INTO TABLE information
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(
  curriculum, docx_id, pdf_id,
  finish_info, finish_course, curr_id,
  faculty, curr_name_th, curr_name_en,
  degree_full_th, degree_full_en,
  degree_abr_th, degree_abr_en,
  campus, curr_category, curr_type, lang, mou,
  first_open_semester, first_open_year,
  careers, expense_type, student_nation, qualification_collegian,
  max_semester, day_class, type_class,
  total_credits, gen_ed_credits, spec_credits, elec_credits, free_elec_credits,
  count_research, count_academic_paper,
  count_lecturer_academic, count_lecturer_full, count_lecturer_extra, count_staff,
  other_grade, criteria_graduate,
  curr_qa
);

-- =========================
-- course.csv
-- =========================
LOAD DATA LOCAL INFILE '/docker-entrypoint-initdb.d/course.csv'
INTO TABLE course
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(
  curriculum, course_type,
  th_abv, th_name, eng_abv, eng_name,
  credit, lect_hours, practice_hours, self_hours,
  th_desc, eng_desc,
  prerequisite
);

-- =========================
-- qualification_responsible.csv
-- =========================
LOAD DATA LOCAL INFILE '/docker-entrypoint-initdb.d/qualification_responsible.csv'
INTO TABLE qualification_responsible
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(
  curriculum,
  qualification_responsible_position,
  name_responsible,
  degree_reponsible,
  program_responsible,
  institute_responsible,
  year_graduate_responsible
);

-- =========================
-- plo.csv
-- คอลัมน์แรกชื่อ 'Table Names' ไม่ต้องการนำเข้า
-- =========================
LOAD DATA LOCAL INFILE '/docker-entrypoint-initdb.d/plo.csv'
INTO TABLE plo
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(
  @dummy,        -- Table Names (ignore)
  curriculum,
  type_plo,
  num_plo,
  detail_plo
);
