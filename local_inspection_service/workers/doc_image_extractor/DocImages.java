import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import org.apache.poi.hwpf.HWPFDocument;
import org.apache.poi.hwpf.usermodel.Picture;
import org.apache.poi.util.IOUtils;

/** Export embedded picture payloads only. No page rendering, macros or links. */
public final class DocImages {
    public static void main(String[] args) {
        try { extract(args); }
        catch (Exception error) {
            // Do not print document text, passwords or arbitrary exception payloads.
            System.err.println("DOC_IMAGE_EXTRACTION_FAILED:" + error.getClass().getSimpleName());
            System.exit(2);
        }
    }
    static void extract(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException();
        Path input = Paths.get(args[0]), output = Paths.get(args[1]);
        if (Files.size(input) > 30L * 1024 * 1024) throw new IOException("input limit");
        IOUtils.setByteArrayMaxOverride(100 * 1024 * 1024);
        try (InputStream stream = Files.newInputStream(input);
             HWPFDocument document = new HWPFDocument(stream);
             ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(output, StandardOpenOption.CREATE_NEW))) {
            List<Picture> pictures = document.getPicturesTable().getAllPictures();
            if (pictures.isEmpty() || pictures.size() > 500) throw new IOException("picture count");
            StringBuilder manifest = new StringBuilder("doc-images-v1\tpoi-5.5.1\n");
            long total = 0; int ordinal = 0;
            for (Picture picture : pictures) {
                // getContent decompresses the embedded payload; it does not rasterize
                // Word shapes, apply Word crop settings, or composite overlaid text.
                byte[] bytes = picture.getContent();
                if (bytes == null || bytes.length == 0) throw new IOException("empty picture");
                total += bytes.length;
                if (bytes.length > 30 * 1024 * 1024 || total > 100L * 1024 * 1024) throw new IOException("output limit");
                String name = String.format(Locale.ROOT, "image%04d.bin", ++ordinal);
                zip.putNextEntry(new ZipEntry(name)); zip.write(bytes); zip.closeEntry();
                manifest.append(name).append('\t').append(picture.getStartOffset()).append('\n');
            }
            zip.putNextEntry(new ZipEntry("manifest.tsv"));
            zip.write(manifest.toString().getBytes(StandardCharsets.UTF_8)); zip.closeEntry();
        }
    }
}
