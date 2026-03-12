def capture(String outputPath = '.pipelinehealer-log-excerpt.txt', Closure body) {
  tee(file: outputPath) {
    body()
  }
}

def writeLogExcerpt(String outputPath = '.pipelinehealer-log-excerpt.txt', int maxLines = 200, int maxChars = 20000) {
  if (!fileExists(outputPath)) {
    echo 'PipelineHealer bridge evidence: no captured excerpt file is available yet.'
    return false
  }

  String content = readFile(outputPath)
  if (content == null) {
    echo 'PipelineHealer bridge evidence: captured excerpt file could not be read.'
    return false
  }

  if (maxChars > 0 && content.length() > maxChars) {
    content = content.substring(content.length() - maxChars)
  }

  List<String> lines = content.readLines()
  if (maxLines > 0 && lines.size() > maxLines) {
    lines = lines.takeRight(maxLines)
  }

  String excerpt = lines.join('\n')
  writeFile file: outputPath, text: excerpt ? "${excerpt}\n" : ''
  return true
}

return this
