CREATE TABLE IF NOT EXISTS "__EFMigrationsHistory" (
    "MigrationId" character varying(150) NOT NULL,
    "ProductVersion" character varying(32) NOT NULL,
    CONSTRAINT "PK___EFMigrationsHistory" PRIMARY KEY ("MigrationId")
);

START TRANSACTION;


DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20231129225733_CreateUsersTable') THEN
    CREATE TABLE "Devices" (
        "Id" uuid NOT NULL,
        "UserId" uuid NOT NULL,
        "DeviceId" text NOT NULL,
        "DeviceToken" text NOT NULL,
        CONSTRAINT "PK_Devices" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20231129225733_CreateUsersTable') THEN
    CREATE TABLE "Users" (
        "Id" uuid NOT NULL,
        "Email" text NOT NULL,
        "Password" text NOT NULL,
        "Username" text NOT NULL,
        "ReferralCode" text NOT NULL,
        "CreatedDate" timestamp with time zone NOT NULL,
        "ResetToken" text NULL,
        "ResetTokenExpires" timestamp with time zone NULL,
        "SocialId" text NULL,
        "SocialPlatform" text NULL,
        "ProfilePic" text NULL,
        CONSTRAINT "PK_Users" PRIMARY KEY ("Id")
    );
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20231129225733_CreateUsersTable') THEN
    INSERT INTO "__EFMigrationsHistory" ("MigrationId", "ProductVersion")
    VALUES ('20231129225733_CreateUsersTable', '7.0.18');
    END IF;
END $EF$;
COMMIT;

START TRANSACTION;


DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20240105022534_InitialCreate') THEN
    INSERT INTO "__EFMigrationsHistory" ("MigrationId", "ProductVersion")
    VALUES ('20240105022534_InitialCreate', '7.0.18');
    END IF;
END $EF$;
COMMIT;

START TRANSACTION;


DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20250119163924_AddDateOfBirthToUser') THEN
    ALTER TABLE "Users" ADD "DateOfBirth" timestamp with time zone NULL;
    END IF;
END $EF$;

DO $EF$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM "__EFMigrationsHistory" WHERE "MigrationId" = '20250119163924_AddDateOfBirthToUser') THEN
    INSERT INTO "__EFMigrationsHistory" ("MigrationId", "ProductVersion")
    VALUES ('20250119163924_AddDateOfBirthToUser', '7.0.18');
    END IF;
END $EF$;
COMMIT;

