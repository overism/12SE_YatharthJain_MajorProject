BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS "users" (
	"userID" INTEGER,
	"userName" TEXT NOT NULL,
	"userEmail" TEXT NOT NULL,
	"userPassword" TEXT NOT NULL,
	"userPfp" BLOB,
	"userBio" TEXT,
	"userSettings" TEXT,
	PRIMARY KEY("userID" AUTOINCREMENT)
);

CREATE TABLE IF NOT EXISTS "google_creds" (
	"userID" INTEGER PRIMARY KEY,
	"accessToken" TEXT,
	"refreshToken" TEXT,
	"expiry" TEXT,
	"expiresAt" INTEGER,
	"calendarID" TEXT DEFAULT 'primary',
	"syncToken" TEXT,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "tasks" (
	"taskID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"userID" INTEGER NOT NULL,
	"subjectID" INTEGER NOT NULL,
	"title" TEXT NOT NULL,
	"description" TEXT,
	"dueDate" DATETIME,
	"taskType" TEXT DEFAULT 'Homework',
	"progress" INTEGER DEFAULT 0,
	"daysRemaining" INTEGER DEFAULT 0,
	"status" TEXT DEFAULT 'pending' CHECK("status" IN ('pending', 'in_progress', 'completed')),
	"eventID" INTEGER,
	"createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE,
	FOREIGN KEY("subjectID") REFERENCES "subjects"("subjectID") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "subjects" (
	"subjectID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"userID" INTEGER NOT NULL,
	"subjectName" TEXT NOT NULL,
	"colourScheme" TEXT DEFAULT 'orange',
	"sortOrder" INTEGER DEFAULT 0,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "events" (
	"eventID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"googleEventID" TEXT,
	"userID" INTEGER NOT NULL,
	"title" TEXT NOT NULL,
	"description" TEXT,
	"color" TEXT DEFAULT '#f6863b',
	"startTime" DATETIME NOT NULL,
	"endTime" DATETIME NOT NULL,
	"isAllDay" BOOLEAN,
	"source" TEXT CHECK("source" IN ('user', 'google', 'auto')),
	"isDeleted" BOOLEAN DEFAULT 0,
	"lastSynced" DATETIME,
	"createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	"updatedAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "schedules" (
	"scheduleID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"userID" INTEGER NOT NULL,
	"title" TEXT,
	"isActive" BOOLEAN DEFAULT 1,
	"createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "timer_presets" (
	"presetID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"userID" INTEGER NOT NULL,
	"presetName" TEXT NOT NULL,
	"durationSeconds" INTEGER NOT NULL,
	"description" TEXT,
	"isDefault" BOOLEAN DEFAULT 0,
	"createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	"updatedAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "timer_sessions" (
	"sessionID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"userID" INTEGER NOT NULL,
	"subjectID" INTEGER NOT NULL,
	"presetID" INTEGER,
	"durationSeconds" INTEGER NOT NULL,
	"timeSpentSeconds" INTEGER NOT NULL DEFAULT 0,
	"status" TEXT DEFAULT 'completed' CHECK("status" IN ('in_progress', 'paused', 'completed', 'abandoned')),
	"notes" TEXT,
	"startTime" DATETIME DEFAULT CURRENT_TIMESTAMP,
	"endTime" DATETIME,
	"createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	"updatedAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE,
	FOREIGN KEY("subjectID") REFERENCES "subjects"("subjectID") ON DELETE CASCADE,
	FOREIGN KEY("presetID") REFERENCES "timer_presets"("presetID") ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS "flashcard_decks" (
	"deckID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"userID" INTEGER NOT NULL,
	"title" TEXT NOT NULL,
	"subject" TEXT NOT NULL DEFAULT 'General',
	"module" TEXT NOT NULL DEFAULT 'General',
	"cardCount" INTEGER NOT NULL DEFAULT 0,
	"createdAt" TEXT NOT NULL DEFAULT (datetime('now')),
	"updatedAt" TEXT NOT NULL DEFAULT (datetime('now')),
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "flashcards" (
	"cardID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"deckID" INTEGER NOT NULL,
	"userID" INTEGER NOT NULL,
	"question" TEXT NOT NULL,
	"answer" TEXT NOT NULL,
	"hint" TEXT,
	"sortOrder" INTEGER NOT NULL DEFAULT 0,
	"createdAt" TEXT NOT NULL DEFAULT (datetime('now')),
	FOREIGN KEY("deckID") REFERENCES "flashcard_decks"("deckID") ON DELETE CASCADE,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "flashcard_results" (
	"resultID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"deckID" INTEGER NOT NULL,
	"userID" INTEGER NOT NULL,
	"knew" INTEGER NOT NULL DEFAULT 0,
	"unsure" INTEGER NOT NULL DEFAULT 0,
	"missed" INTEGER NOT NULL DEFAULT 0,
	"totalCards" INTEGER NOT NULL DEFAULT 0,
	"studiedAt" TEXT NOT NULL DEFAULT (datetime('now')),
	FOREIGN KEY("deckID") REFERENCES "flashcard_decks"("deckID") ON DELETE CASCADE,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "chat_sessions" (
	"sessionID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"userID" INTEGER NOT NULL,
	"title" TEXT NOT NULL DEFAULT 'Untitled Chat',
	"subject" TEXT DEFAULT 'General',
	"module" TEXT DEFAULT 'General',
	"messageCount" INTEGER DEFAULT 0,
	"createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	"updatedAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "chat_messages" (
	"messageID" INTEGER PRIMARY KEY AUTOINCREMENT,
	"sessionID" INTEGER NOT NULL,
	"userID" INTEGER NOT NULL,
	"role" TEXT NOT NULL CHECK("role" IN ('user', 'assistant')),
	"mode" TEXT DEFAULT 'tutor',
	"content" TEXT NOT NULL,
	"sources" TEXT,
	"createdAt" DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY("sessionID") REFERENCES "chat_sessions"("sessionID") ON DELETE CASCADE,
	FOREIGN KEY("userID") REFERENCES "users"("userID") ON DELETE CASCADE
);

INSERT INTO "users" VALUES (1,'admin','admin@DustyAI.com', 'DustyAdminPass123!', NULL, 'Administrator account', NULL);
INSERT INTO "subjects" ("userID", "subjectName", "colourScheme", "sortOrder") VALUES
	(1, 'Software Engineering', 'orange', 1),
	(1, 'Mathematics', 'blue', 2),
	(1, 'English', 'green', 3),
	(1, 'Science', 'red', 4),
	(1, 'Humanities', 'purple', 5);
COMMIT;
