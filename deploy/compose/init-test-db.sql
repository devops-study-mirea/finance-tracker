-- Выполняется один раз при первом создании volume.
-- Отдельная база под тесты, чтобы прогон pytest не сносил твои реальные данные.
CREATE DATABASE finance_test OWNER finance;
