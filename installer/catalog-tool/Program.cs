using System.Security.Cryptography;
using System.Text.Json;
using Thuai10.Launcher.Services;

if (args.Length != 3)
{
    Console.Error.WriteLine("用法: catalog-tool <选手包目录> <输出清单.json> <版本号>");
    return 2;
}

string root = Path.GetFullPath(args[0]);
string output = Path.GetFullPath(args[1]);
string version = args[2];
if (!Directory.Exists(root) || string.IsNullOrWhiteSpace(version))
{
    Console.Error.WriteLine("选手包目录不存在，或版本号为空。");
    return 2;
}

PackageCatalog catalog = new() { Version = version };
foreach (string file in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
    .OrderBy(path => path, StringComparer.OrdinalIgnoreCase))
{
    string relative = Path.GetRelativePath(root, file).Replace('\\', '/');
    if (relative.StartsWith('.') || relative.EndsWith(".part", StringComparison.OrdinalIgnoreCase)
        || relative.EndsWith(".tmp", StringComparison.OrdinalIgnoreCase)
        || (File.GetAttributes(file) & FileAttributes.ReparsePoint) != 0)
    {
        continue;
    }

    await using FileStream stream = File.OpenRead(file);
    catalog.Files.Add(new PackageFile
    {
        Path = relative,
        Url = string.Join('/', relative.Split('/').Select(Uri.EscapeDataString)),
        Size = stream.Length,
        Sha256 = Convert.ToHexStringLower(await SHA256.HashDataAsync(stream))
    });
}

if (catalog.Files.Count == 0)
{
    Console.Error.WriteLine("没有可发布的文件。");
    return 2;
}

Directory.CreateDirectory(Path.GetDirectoryName(output)!);
await File.WriteAllTextAsync(output, JsonSerializer.Serialize(catalog,
    new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, WriteIndented = true }));
Console.WriteLine($"已生成 {catalog.Files.Count} 个文件的清单：{output}");
return 0;
