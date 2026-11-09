import { sqliteTable, text, integer, primaryKey } from 'drizzle-orm/sqlite-core';
export const clients=sqliteTable('clients',{
 id:text('id').primaryKey(), clientHash:text('client_hash').notNull().unique(), tokenHash:text('token_hash').notNull(),
 expiresAt:integer('expires_at').notNull(), disabled:integer('disabled').notNull().default(0)
});
export const quotas=sqliteTable('quotas',{
 bucket:text('bucket').notNull(), period:text('period').notNull(), used:integer('used').notNull().default(0)
},t=>[primaryKey({columns:[t.bucket,t.period]})]);
export const requests=sqliteTable('requests',{
 id:text('id').primaryKey(), tokenId:text('token_id').notNull(), status:text('status').notNull(), createdAt:integer('created_at').notNull()
});
