BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS "users" (
	"userID"	INTEGER,
	"userName"	TEXT NOT NULL,
	"userEmail"	TEXT NOT NULL,
	"userPassword"	TEXT NOT NULL,
	"userPfp"	BLOB,
	"userBio"	TEXT,
	"userSettings"	TEXT,
	PRIMARY KEY("userID" AUTOINCREMENT)
);

INSERT INTO "users" VALUES (1,'admin','admin@DustyAI.com', 'DustyAdminPass123!', NULL, 'Administrator account', NULL);
COMMIT;