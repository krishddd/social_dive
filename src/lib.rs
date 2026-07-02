use pyo3::prelude::*;
use pyo3::types::PyDict;
use scraper::{Html, Selector};
use std::collections::VecDeque;

// ---------------------------------------------------------------------------
// html_to_markdown: high-speed HTML → clean Markdown conversion
// ---------------------------------------------------------------------------

/// Convert an HTML string to clean Markdown text.
///
/// This is a simplified but fast converter that handles the most common HTML
/// elements: headings, paragraphs, links, lists, code blocks, emphasis, and
/// images.  It is intentionally not a full spec-compliant converter — the goal
/// is speed and "good enough" output for LLM consumption.
#[pyfunction]
fn html_to_markdown(html: &str) -> String {
    let document = Html::parse_document(html);
    let mut output = String::with_capacity(html.len() / 2);

    // Walk the DOM tree in document order
    let root = document.root_element();
    walk_node(&root, &mut output, &WalkState::default());

    // Clean up excessive blank lines
    let mut cleaned = String::with_capacity(output.len());
    let mut blank_count = 0u32;
    for line in output.lines() {
        if line.trim().is_empty() {
            blank_count += 1;
            if blank_count <= 2 {
                cleaned.push('\n');
            }
        } else {
            blank_count = 0;
            cleaned.push_str(line);
            cleaned.push('\n');
        }
    }

    cleaned.trim().to_string()
}

#[derive(Default, Clone)]
struct WalkState {
    in_pre: bool,
    in_code: bool,
    list_depth: u32,
    ordered: bool,
    item_index: u32,
}

fn walk_node(node: &scraper::ElementRef, out: &mut String, state: &WalkState) {
    for child in node.children() {
        match child.value() {
            scraper::node::Node::Text(text) => {
                let t = text.text.as_ref();
                if state.in_pre || state.in_code {
                    out.push_str(t);
                } else {
                    // Collapse whitespace
                    let collapsed: String = t.split_whitespace().collect::<Vec<_>>().join(" ");
                    if !collapsed.is_empty() {
                        out.push_str(&collapsed);
                    }
                }
            }
            scraper::node::Node::Element(el) => {
                if let Some(elem_ref) = scraper::ElementRef::wrap(child) {
                    let tag = el.name.local.as_ref();
                    let mut next_state = state.clone();

                    match tag {
                        "h1" => {
                            out.push_str("\n\n# ");
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("\n\n");
                        }
                        "h2" => {
                            out.push_str("\n\n## ");
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("\n\n");
                        }
                        "h3" => {
                            out.push_str("\n\n### ");
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("\n\n");
                        }
                        "h4" => {
                            out.push_str("\n\n#### ");
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("\n\n");
                        }
                        "h5" => {
                            out.push_str("\n\n##### ");
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("\n\n");
                        }
                        "h6" => {
                            out.push_str("\n\n###### ");
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("\n\n");
                        }
                        "p" => {
                            out.push_str("\n\n");
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("\n\n");
                        }
                        "br" => {
                            out.push_str("  \n");
                        }
                        "hr" => {
                            out.push_str("\n\n---\n\n");
                        }
                        "a" => {
                            let href = el.attr("href").unwrap_or("#");
                            out.push('[');
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("](");
                            out.push_str(href);
                            out.push(')');
                        }
                        "img" => {
                            let src = el.attr("src").unwrap_or("");
                            let alt = el.attr("alt").unwrap_or("image");
                            out.push_str("![");
                            out.push_str(alt);
                            out.push_str("](");
                            out.push_str(src);
                            out.push(')');
                        }
                        "strong" | "b" => {
                            out.push_str("**");
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("**");
                        }
                        "em" | "i" => {
                            out.push('*');
                            walk_node(&elem_ref, out, &next_state);
                            out.push('*');
                        }
                        "code" => {
                            if !state.in_pre {
                                out.push('`');
                                next_state.in_code = true;
                                walk_node(&elem_ref, out, &next_state);
                                out.push('`');
                            } else {
                                walk_node(&elem_ref, out, &next_state);
                            }
                        }
                        "pre" => {
                            out.push_str("\n\n```\n");
                            next_state.in_pre = true;
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("\n```\n\n");
                        }
                        "blockquote" => {
                            out.push_str("\n\n> ");
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str("\n\n");
                        }
                        "ul" => {
                            next_state.list_depth += 1;
                            next_state.ordered = false;
                            next_state.item_index = 0;
                            out.push('\n');
                            walk_node(&elem_ref, out, &next_state);
                            out.push('\n');
                        }
                        "ol" => {
                            next_state.list_depth += 1;
                            next_state.ordered = true;
                            next_state.item_index = 0;
                            out.push('\n');
                            walk_node(&elem_ref, out, &next_state);
                            out.push('\n');
                        }
                        "li" => {
                            let indent = "  ".repeat((state.list_depth.saturating_sub(1)) as usize);
                            if state.ordered {
                                let idx = state.item_index + 1;
                                out.push_str(&format!("\n{}{}. ", indent, idx));
                            } else {
                                out.push_str(&format!("\n{}- ", indent));
                            }
                            walk_node(&elem_ref, out, &next_state);
                        }
                        "table" | "thead" | "tbody" | "tfoot" => {
                            walk_node(&elem_ref, out, &next_state);
                        }
                        "tr" => {
                            out.push_str("\n| ");
                            walk_node(&elem_ref, out, &next_state);
                        }
                        "th" | "td" => {
                            walk_node(&elem_ref, out, &next_state);
                            out.push_str(" | ");
                        }
                        // Skip non-content elements
                        "script" | "style" | "noscript" | "nav" | "footer" | "header" => {}
                        // For everything else, just recurse into children
                        _ => {
                            walk_node(&elem_ref, out, &next_state);
                        }
                    }
                }
            }
            _ => {}
        }
    }
}

// ---------------------------------------------------------------------------
// parallel_fetch: concurrent HTTP fetcher that releases the GIL
// ---------------------------------------------------------------------------

/// Result of fetching a single URL.
#[pyclass]
#[derive(Clone)]
struct FetchResult {
    #[pyo3(get)]
    url: String,
    #[pyo3(get)]
    status: u16,
    #[pyo3(get)]
    body: String,
    #[pyo3(get)]
    error: String,
    #[pyo3(get)]
    ok: bool,
}

/// Fetch multiple URLs concurrently using Rust async I/O.
///
/// Releases the Python GIL during network I/O so other Python threads can
/// continue running.  Returns a list of `FetchResult` objects in the same
/// order as the input URLs.
#[pyfunction]
#[pyo3(signature = (urls, timeout_ms = 30000, max_concurrent = 10))]
fn parallel_fetch(
    py: Python<'_>,
    urls: Vec<String>,
    timeout_ms: u64,
    max_concurrent: usize,
) -> PyResult<Vec<FetchResult>> {
    py.allow_threads(|| {
        let rt = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        let results = rt.block_on(async {
            let client = reqwest::Client::builder()
                .timeout(std::time::Duration::from_millis(timeout_ms))
                .user_agent("SocialDive/0.1.0")
                .build()
                .unwrap();

            let semaphore = std::sync::Arc::new(tokio::sync::Semaphore::new(max_concurrent));
            let mut handles = Vec::with_capacity(urls.len());

            for url in urls.iter() {
                let client = client.clone();
                let url = url.clone();
                let sem = semaphore.clone();

                handles.push(tokio::spawn(async move {
                    let _permit = sem.acquire().await.unwrap();
                    match client.get(&url).send().await {
                        Ok(resp) => {
                            let status = resp.status().as_u16();
                            match resp.text().await {
                                Ok(body) => FetchResult {
                                    url,
                                    status,
                                    body,
                                    error: String::new(),
                                    ok: true,
                                },
                                Err(e) => FetchResult {
                                    url,
                                    status,
                                    body: String::new(),
                                    error: format!("Body read error: {}", e),
                                    ok: false,
                                },
                            }
                        }
                        Err(e) => FetchResult {
                            url,
                            status: 0,
                            body: String::new(),
                            error: format!("Request error: {}", e),
                            ok: false,
                        },
                    }
                }));
            }

            let mut results = Vec::with_capacity(handles.len());
            for handle in handles {
                results.push(handle.await.unwrap());
            }
            results
        });

        Ok(results)
    })
}

// ---------------------------------------------------------------------------
// Python module registration
// ---------------------------------------------------------------------------

/// Social Dive Rust core — high-performance HTML parsing and concurrent I/O.
#[pymodule]
fn _social_dive_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(html_to_markdown, m)?)?;
    m.add_function(wrap_pyfunction!(parallel_fetch, m)?)?;
    m.add_class::<FetchResult>()?;
    Ok(())
}
