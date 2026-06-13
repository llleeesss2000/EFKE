use rusqlite::Connection;
use clap::Parser;
use std::path::Path;

#[derive(Parser)]
#[command(name = "efke-meta", about = "Batch metadata operations for EFKE")]
struct Args {
    #[command(subcommand)]
    command: Command,
}

#[derive(clap::Subcommand)]
enum Command {
    /// Count records in tables
    Stats {
        #[arg(short, long, default_value = "server_data/metadata.db")]
        db: String,
    },
    /// Find duplicate files by hash
    Duplicates {
        #[arg(short, long, default_value = "server_data/metadata.db")]
        db: String,
    },
    /// Show project summary
    Summary {
        #[arg(short, long)]
        project_id: String,
        #[arg(short, long, default_value = "server_data/metadata.db")]
        db: String,
    },
    /// Orphan files (in DB but not on disk)
    Orphans {
        #[arg(short, long, default_value = "server_data/metadata.db")]
        db: String,
    },
}

fn main() {
    let args = Args::parse();
    match args.command {
        Command::Stats { db } => cmd_stats(&db),
        Command::Duplicates { db } => cmd_duplicates(&db),
        Command::Summary { project_id, db } => cmd_summary(&db, &project_id),
        Command::Orphans { db } => cmd_orphans(&db),
    }
}

fn cmd_stats(db_path: &str) {
    let conn = Connection::open(db_path).expect("Cannot open DB");
    let tables = vec!["users", "projects", "files", "chunks", "blocks", "assets", "ai_knowledge", "wiki_pages", "knowledge_graph", "search_history", "sessions"];
    println!("=== Database Statistics ===");
    for table in &tables {
        let count: i64 = conn.query_row(&format!("SELECT COUNT(*) FROM {}", table), [], |row| row.get(0)).unwrap_or(0);
        println!("  {:20} {:>8}", table, count);
    }
    let total_chunks: i64 = conn.query_row("SELECT COUNT(*) FROM chunks", [], |row| row.get(0)).unwrap_or(0);
    let total_blocks: i64 = conn.query_row("SELECT COUNT(*) FROM blocks", [], |row| row.get(0)).unwrap_or(0);
    let total_assets: i64 = conn.query_row("SELECT COUNT(*) FROM assets", [], |row| row.get(0)).unwrap_or(0);
    println!("  ---");
    println!("  {:20} {:>8}", "total chunks", total_chunks);
    println!("  {:20} {:>8}", "total blocks", total_blocks);
    println!("  {:20} {:>8}", "total assets", total_assets);
}

fn cmd_duplicates(db_path: &str) {
    let conn = Connection::open(db_path).expect("Cannot open DB");
    let mut stmt = conn.prepare("SELECT source_hash, COUNT(*) as cnt, GROUP_CONCAT(filename) as files FROM files GROUP BY source_hash HAVING cnt > 1").unwrap();
    let rows = stmt.query_map([], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?, row.get::<_, String>(2)?))
    }).unwrap();
    println!("=== Duplicate Files ===");
    let mut found = false;
    for row in rows {
        let (hash, count, files) = row.unwrap();
        println!("  Hash: {} ({} files): {}", &hash[..16], count, files);
        found = true;
    }
    if !found { println!("  No duplicates found."); }
}

fn cmd_summary(db_path: &str, project_id: &str) {
    let conn = Connection::open(db_path).expect("Cannot open DB");
    let name: String = conn.query_row("SELECT name FROM projects WHERE id=?", [project_id], |row| row.get(0)).unwrap_or_default();
    if name.is_empty() { println!("Project not found"); return; }
    let files: i64 = conn.query_row("SELECT COUNT(*) FROM files WHERE project_id=?", [project_id], |row| row.get(0)).unwrap_or(0);
    let chunks: i64 = conn.query_row("SELECT COUNT(*) FROM chunks WHERE project_id=?", [project_id], |row| row.get(0)).unwrap_or(0);
    let blocks: i64 = conn.query_row("SELECT COUNT(*) FROM blocks WHERE project_id=?", [project_id], |row| row.get(0)).unwrap_or(0);
    let assets: i64 = conn.query_row("SELECT COUNT(*) FROM assets WHERE project_id=?", [project_id], |row| row.get(0)).unwrap_or(0);
    let wiki: i64 = conn.query_row("SELECT COUNT(*) FROM wiki_pages WHERE project_id=?", [project_id], |row| row.get(0)).unwrap_or(0);
    let kg: i64 = conn.query_row("SELECT COUNT(*) FROM knowledge_graph WHERE project_id=?", [project_id], |row| row.get(0)).unwrap_or(0);
    println!("=== Project: {} ===", name);
    println!("  Files:         {}", files);
    println!("  Chunks:        {}", chunks);
    println!("  Blocks:        {}", blocks);
    println!("  Assets:        {}", assets);
    println!("  Wiki pages:    {}", wiki);
    println!("  KG entities:   {}", kg);
}

fn cmd_orphans(db_path: &str) {
    let conn = Connection::open(db_path).expect("Cannot open DB");
    let mut stmt = conn.prepare("SELECT id, source_path FROM files").unwrap();
    let rows: Vec<(String, String)> = stmt.query_map([], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
    }).unwrap().filter_map(|r| r.ok()).collect();
    let mut orphans = 0;
    for (id, path) in &rows {
        if !Path::new(path).exists() {
            println!("  ORPHAN: {} -> {}", id, path);
            orphans += 1;
        }
    }
    if orphans == 0 { println!("  No orphan files found."); }
    else { println!("  Total orphans: {}", orphans); }
}
