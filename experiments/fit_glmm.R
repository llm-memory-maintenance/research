# Maximum-likelihood binomial-logit GLMM fits (lme4::glmer, Laplace) for the CRST power simulation.
# Usage: Rscript fit_glmm.R input.json output.json
# Formulas, numeric contrast columns and data come from experiments/power_simulation.py; this script only fits and
# reports raw evidence. It computes no estimand, test or decision.
suppressPackageStartupMessages({
  library(lme4)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("Usage: Rscript fit_glmm.R input.json output.json")
input <- fromJSON(args[[1]], simplifyVector = FALSE)
settings <- input$control
control <- glmerControl(
  optimizer = settings$optimizer,
  optCtrl = list(maxfun = settings$maxfun),
  check.conv.grad = .makeCC("warning", tol = settings$grad_tol, relTol = NULL),
  check.conv.singular = .makeCC(action = "ignore", tol = settings$singular_tol)
)

fit_one <- function(formula, frame) {
  warnings <- character()
  messages <- character()
  collect <- function(expr) withCallingHandlers(expr,
    warning = function(w) { warnings <<- c(warnings, conditionMessage(w)); invokeRestart("muffleWarning") },
    message = function(m) { messages <<- c(messages, conditionMessage(m)); invokeRestart("muffleMessage") })
  fit <- tryCatch(collect(glmer(as.formula(formula), data = frame, family = binomial("logit"),
                                control = control, nAGQ = settings$nagq)),
                  error = function(e) e)
  if (inherits(fit, "error")) {
    return(list(status = "error", error = conditionMessage(fit), warnings = I(warnings), messages = I(messages)))
  }
  fit_warnings <- warnings
  vc <- tryCatch(collect(as.matrix(vcov(fit))), error = function(e) NULL)
  re_all <- as.data.frame(VarCorr(fit))
  # Rows with a second variable are estimated correlations; a diagonal (||) structure must have none.
  re <- re_all[is.na(re_all$var2), ]
  lme4_messages <- fit@optinfo$conv$lme4$messages
  optimizer_code <- fit@optinfo$conv$opt
  list(
    status = "fitted",
    beta = as.list(fixef(fit)),
    vcov_names = if (is.null(vc)) NULL else I(rownames(vc)),
    vcov = if (is.null(vc)) NULL else lapply(seq_len(nrow(vc)), function(i) I(unname(vc[i, ]))),
    re_components = I(as.character(re$var1)),
    re_sd = I(re$sdcor),
    re_groups = I(as.character(re$grp)),
    re_correlation_terms = sum(!is.na(re_all$var2)),
    loglik = as.numeric(logLik(fit)),
    singular = isSingular(fit, tol = settings$singular_tol),
    optimizer_code = if (length(optimizer_code) == 1) as.integer(optimizer_code) else NA_integer_,
    convergence_warnings = I(c(fit_warnings, if (is.null(lme4_messages)) character() else lme4_messages)),
    vcov_warnings = I(setdiff(warnings, fit_warnings)),
    messages = I(messages)
  )
}

results <- lapply(input$jobs, function(job) {
  frame <- as.data.frame(lapply(job$data, unlist))
  frame$scenario <- factor(frame$scenario)
  list(job_id = job$job_id,
       fits = lapply(job$formulas, fit_one, frame = frame))
})

versions <- list(R = R.version.string, lme4 = as.character(packageVersion("lme4")),
                 Matrix = as.character(packageVersion("Matrix")),
                 jsonlite = as.character(packageVersion("jsonlite")))
writeLines(toJSON(list(versions = versions, results = results), auto_unbox = TRUE, digits = NA,
                  null = "null", na = "null"), args[[2]])
