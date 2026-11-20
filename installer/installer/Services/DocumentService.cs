namespace Thuai10.Launcher.Services;

public sealed class DocumentService
{
    public IReadOnlyList<string> List(string packageRoot)
    {
        string docs = Path.Combine(packageRoot, "docs");
        if (!Directory.Exists(docs))
        {
            return Array.Empty<string>();
        }

        return Directory.EnumerateFiles(docs, "*.md", SearchOption.AllDirectories)
            .Select(path => Path.GetRelativePath(docs, path))
            .OrderBy(path => path, StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    public async Task<string> ReadAsync(string packageRoot, string relative, CancellationToken token)
    {
        string docs = Path.GetFullPath(Path.Combine(packageRoot, "docs"));
        if (Directory.Exists(docs)
            && (File.GetAttributes(docs) & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException("文档目录是符号链接，拒绝读取。");
        }

        string path = Path.GetFullPath(Path.Combine(docs, relative));
        string prefix = Path.TrimEndingDirectorySeparator(docs) + Path.DirectorySeparatorChar;
        if (!path.StartsWith(prefix, OperatingSystem.IsWindows()
                ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal)
            || !path.EndsWith(".md", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("文档路径不安全。");
        }

        string current = docs;
        foreach (string segment in relative.Replace('\\', '/').Split('/'))
        {
            if (segment.Length == 0 || segment is "." or "..")
            {
                throw new InvalidDataException("文档路径不安全。");
            }

            current = Path.Combine(current, segment);
            if ((File.Exists(current) || Directory.Exists(current))
                && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException("拒绝读取符号链接文档。");
            }
        }

        return await File.ReadAllTextAsync(path, token);
    }
}
