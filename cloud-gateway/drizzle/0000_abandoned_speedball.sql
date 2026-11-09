CREATE TABLE `clients` (
	`id` text PRIMARY KEY NOT NULL,
	`client_hash` text NOT NULL,
	`token_hash` text NOT NULL,
	`expires_at` integer NOT NULL,
	`disabled` integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `clients_client_hash_unique` ON `clients` (`client_hash`);--> statement-breakpoint
CREATE TABLE `quotas` (
	`bucket` text NOT NULL,
	`period` text NOT NULL,
	`used` integer DEFAULT 0 NOT NULL,
	PRIMARY KEY(`bucket`, `period`)
);
--> statement-breakpoint
CREATE TABLE `requests` (
	`id` text PRIMARY KEY NOT NULL,
	`token_id` text NOT NULL,
	`status` text NOT NULL,
	`created_at` integer NOT NULL
);
