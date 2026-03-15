using System.Text.Json;
using Realms;

const ulong schemaVersion = 51;

if (args.Length < 2)
{
    Console.Error.WriteLine("Usage: CollectionRealmExtractor <realm-path> <output-json-path>");
    return 1;
}

string realmPath = Path.GetFullPath(args[0]);
string outputPath = Path.GetFullPath(args[1]);

if (!File.Exists(realmPath))
{
    Console.Error.WriteLine($"Realm file not found: {realmPath}");
    return 2;
}

Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);

var configuration = new RealmConfiguration(realmPath)
{
    IsReadOnly = true,
    SchemaVersion = schemaVersion,
};

using var realm = Realm.GetInstance(configuration);

var beatmapsByMd5 = realm.All<BeatmapInfo>()
                        .Where(b => b.MD5Hash != null && b.MD5Hash != string.Empty)
                        .AsEnumerable()
                        .GroupBy(b => b.MD5Hash, StringComparer.OrdinalIgnoreCase)
                        .ToDictionary(group => group.Key, group => group.First(), StringComparer.OrdinalIgnoreCase);

var collections = realm.All<BeatmapCollection>()
                       .OrderBy(c => c.Name)
                       .AsEnumerable()
                       .Select(collection =>
                       {
                           var items = new List<BeatmapOutputItem>();

                           foreach (string md5 in collection.BeatmapMD5Hashes)
                           {
                               if (beatmapsByMd5.TryGetValue(md5, out var beatmap))
                               {
                                   items.Add(new BeatmapOutputItem
                                   {
                                       Md5 = md5,
                                       Title = beatmap.Metadata?.Title ?? string.Empty,
                                       TitleUnicode = beatmap.Metadata?.TitleUnicode ?? string.Empty,
                                       Artist = beatmap.Metadata?.Artist ?? string.Empty,
                                       ArtistUnicode = beatmap.Metadata?.ArtistUnicode ?? string.Empty,
                                       BeatmapId = beatmap.OnlineID > 0 ? beatmap.OnlineID : null,
                                       BeatmapSetId = beatmap.BeatmapSet?.OnlineID > 0 ? beatmap.BeatmapSet.OnlineID : null,
                                       StarRating = beatmap.StarRating >= 0 ? beatmap.StarRating : null,
                                       CircleSize = beatmap.Difficulty?.CircleSize,
                                       OverallDifficulty = beatmap.Difficulty?.OverallDifficulty,
                                       ApproachRate = beatmap.Difficulty?.ApproachRate,
                                       DrainRate = beatmap.Difficulty?.DrainRate,
                                       TotalObjectCount = beatmap.TotalObjectCount >= 0 ? beatmap.TotalObjectCount : null,
                                       LengthMs = beatmap.Length >= 0 ? beatmap.Length : null,
                                       Bpm = beatmap.BPM > 0 ? beatmap.BPM : null,
                                       StatusInt = beatmap.StatusInt,
                                       DifficultyName = beatmap.DifficultyName ?? string.Empty,
                                       Mapper = beatmap.Metadata?.Author?.Username ?? string.Empty,
                                       RulesetShortName = beatmap.Ruleset?.ShortName ?? string.Empty,
                                       RulesetName = beatmap.Ruleset?.Name ?? string.Empty,
                                       BackgroundUrl = beatmap.BeatmapSet?.OnlineID > 0
                                           ? $"https://assets.ppy.sh/beatmaps/{beatmap.BeatmapSet.OnlineID}/covers/cover.jpg"
                                           : string.Empty,
                                       Missing = false,
                                   });
                               }
                               else
                               {
                                   items.Add(new BeatmapOutputItem
                                   {
                                       Md5 = md5,
                                       Missing = true,
                                   });
                               }
                           }

                           return new CollectionOutput
                           {
                               Id = collection.ID.ToString(),
                               Name = collection.Name,
                               LastModified = collection.LastModified,
                               Items = items,
                           };
                       })
                       .ToList();

var payload = new ExtractedOutput
{
    SourcePath = realmPath,
    GeneratedAt = DateTimeOffset.UtcNow,
    Collections = collections,
};

var options = new JsonSerializerOptions
{
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    WriteIndented = true,
};

File.WriteAllText(outputPath, JsonSerializer.Serialize(payload, options));
return 0;

public class BeatmapCollection : RealmObject
{
    [PrimaryKey]
    public Guid ID { get; set; }

    public string Name { get; set; } = string.Empty;

    public IList<string> BeatmapMD5Hashes { get; } = null!;

    public DateTimeOffset LastModified { get; set; }
}

[MapTo("Beatmap")]
public class BeatmapInfo : RealmObject
{
    [PrimaryKey]
    public Guid ID { get; set; }

    public string DifficultyName { get; set; } = string.Empty;

    public RulesetInfo Ruleset { get; set; } = null!;

    public BeatmapDifficulty Difficulty { get; set; } = null!;

    public BeatmapMetadata Metadata { get; set; } = null!;

    public BeatmapUserSettings UserSettings { get; set; } = null!;

    public BeatmapSetInfo? BeatmapSet { get; set; }

    [MapTo(nameof(Status))]
    public int StatusInt { get; set; }

    [Ignored]
    public int Status
    {
        get => StatusInt;
        set => StatusInt = value;
    }

    [Indexed]
    public int OnlineID { get; set; } = -1;

    public double Length { get; set; }

    public double BPM { get; set; }

    public string Hash { get; set; } = string.Empty;

    public double StarRating { get; set; } = -1;

    [Indexed]
    public string MD5Hash { get; set; } = string.Empty;

    public string OnlineMD5Hash { get; set; } = string.Empty;

    public DateTimeOffset? LastLocalUpdate { get; set; }

    public DateTimeOffset? LastOnlineUpdate { get; set; }

    public bool Hidden { get; set; }

    public int EndTimeObjectCount { get; set; } = -1;

    public int TotalObjectCount { get; set; } = -1;

    public DateTimeOffset? LastPlayed { get; set; }

    public int BeatDivisor { get; set; } = 4;

    public double? EditorTimestamp { get; set; }
}

[MapTo("BeatmapSet")]
public class BeatmapSetInfo : RealmObject
{
    [PrimaryKey]
    public Guid ID { get; set; }

    [Indexed]
    public int OnlineID { get; set; } = -1;

    public DateTimeOffset DateAdded { get; set; }

    public DateTimeOffset? DateSubmitted { get; set; }

    public DateTimeOffset? DateRanked { get; set; }

    public IList<BeatmapInfo> Beatmaps { get; } = null!;

    public IList<RealmNamedFileUsage> Files { get; } = null!;

    [MapTo(nameof(Status))]
    public int StatusInt { get; set; }

    [Ignored]
    public int Status
    {
        get => StatusInt;
        set => StatusInt = value;
    }

    public bool DeletePending { get; set; }

    public string Hash { get; set; } = string.Empty;

    public bool Protected { get; set; }
}

[MapTo("BeatmapMetadata")]
public class BeatmapMetadata : RealmObject
{
    public string Title { get; set; } = string.Empty;

    public string TitleUnicode { get; set; } = string.Empty;

    public string Artist { get; set; } = string.Empty;

    public string ArtistUnicode { get; set; } = string.Empty;

    public RealmUser Author { get; set; } = null!;

    public string Source { get; set; } = string.Empty;

    public string Tags { get; set; } = string.Empty;

    public IList<string> UserTags { get; } = null!;

    public int PreviewTime { get; set; } = -1;

    public string AudioFile { get; set; } = string.Empty;

    public string BackgroundFile { get; set; } = string.Empty;
}

[MapTo("Ruleset")]
public class RulesetInfo : RealmObject
{
    [PrimaryKey]
    public string ShortName { get; set; } = string.Empty;

    [Indexed]
    public int OnlineID { get; set; } = -1;

    public string Name { get; set; } = string.Empty;

    public string InstantiationInfo { get; set; } = string.Empty;

    public int LastAppliedDifficultyVersion { get; set; }

    public bool Available { get; set; }
}

[MapTo("BeatmapDifficulty")]
public class BeatmapDifficulty : EmbeddedObject
{
    public float DrainRate { get; set; } = 5;

    public float CircleSize { get; set; } = 5;

    public float OverallDifficulty { get; set; } = 5;

    public float ApproachRate { get; set; } = 5;

    public double SliderMultiplier { get; set; } = 1.4;

    public double SliderTickRate { get; set; } = 1;
}

public class BeatmapUserSettings : EmbeddedObject
{
    public double Offset { get; set; }
}

public class RealmUser : EmbeddedObject
{
    public int OnlineID { get; set; } = 1;

    public string Username { get; set; } = string.Empty;

    [MapTo(nameof(CountryCode))]
    public string CountryString { get; set; } = "Unknown";

    [Ignored]
    public string CountryCode
    {
        get => CountryString;
        set => CountryString = value;
    }
}

public class RealmNamedFileUsage : EmbeddedObject
{
    public RealmFile File { get; set; } = null!;

    public string Filename { get; set; } = string.Empty;
}

[MapTo("File")]
public class RealmFile : RealmObject
{
    [PrimaryKey]
    public string Hash { get; set; } = string.Empty;
}

public sealed class ExtractedOutput
{
    public string SourcePath { get; set; } = string.Empty;

    public DateTimeOffset GeneratedAt { get; set; }

    public List<CollectionOutput> Collections { get; set; } = new();
}

public sealed class CollectionOutput
{
    public string Id { get; set; } = string.Empty;

    public string Name { get; set; } = string.Empty;

    public DateTimeOffset LastModified { get; set; }

    public List<BeatmapOutputItem> Items { get; set; } = new();
}

public sealed class BeatmapOutputItem
{
    public string Md5 { get; set; } = string.Empty;

    public string Title { get; set; } = string.Empty;

    public string TitleUnicode { get; set; } = string.Empty;

    public string Artist { get; set; } = string.Empty;

    public string ArtistUnicode { get; set; } = string.Empty;

    public int? BeatmapId { get; set; }

    public int? BeatmapSetId { get; set; }

    public double? StarRating { get; set; }

    public float? CircleSize { get; set; }

    public float? OverallDifficulty { get; set; }

    public float? ApproachRate { get; set; }

    public float? DrainRate { get; set; }

    public int? TotalObjectCount { get; set; }

    public double? LengthMs { get; set; }

    public double? Bpm { get; set; }

    public int? StatusInt { get; set; }

    public string DifficultyName { get; set; } = string.Empty;

    public string Mapper { get; set; } = string.Empty;

    public string RulesetShortName { get; set; } = string.Empty;

    public string RulesetName { get; set; } = string.Empty;

    public string BackgroundUrl { get; set; } = string.Empty;

    public bool Missing { get; set; }
}
