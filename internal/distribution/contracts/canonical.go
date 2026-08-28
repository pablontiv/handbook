package contracts

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
)

const maxSafeInteger int64 = 9007199254740991

// StrictParseCanonical parses canonical JSON into dst and rejects the contract
// subset prohibited by Waywarden: BOMs, duplicate keys, trailing bytes, invalid
// UTF-8, floats/exponents, unsafe integers, and any noncanonical reserialization.
func StrictParseCanonical(data []byte, dst any) error {
	value, err := parseStrictJSON(data)
	if err != nil {
		return err
	}
	canonical, err := encodeCanonical(value)
	if err != nil {
		return err
	}
	if !bytes.Equal(data, canonical) {
		return fmt.Errorf("json is not canonical")
	}
	if dst == nil {
		return nil
	}
	decoder := json.NewDecoder(bytes.NewReader(canonical))
	decoder.UseNumber()
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(dst); err != nil {
		return err
	}
	return nil
}

// CanonicalBytes returns compact RFC 8785-subset canonical JSON with sorted
// object keys and no final newline.
func CanonicalBytes(value any) ([]byte, error) {
	if err := rejectUnsupportedGoValues(reflect.ValueOf(value)); err != nil {
		return nil, err
	}
	data, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	parsed, err := parseStrictJSON(data)
	if err != nil {
		return nil, err
	}
	return encodeCanonical(parsed)
}

func parseStrictJSON(data []byte) (any, error) {
	if bytes.HasPrefix(data, []byte{0xEF, 0xBB, 0xBF}) {
		return nil, fmt.Errorf("json byte order mark is not allowed")
	}
	if !utf8.Valid(data) {
		return nil, fmt.Errorf("json is not valid UTF-8")
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	value, err := parseJSONValue(decoder)
	if err != nil {
		return nil, err
	}
	if token, err := decoder.Token(); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("json has trailing token %v", token)
		}
		return nil, err
	}
	return value, nil
}

func parseJSONValue(decoder *json.Decoder) (any, error) {
	token, err := decoder.Token()
	if err != nil {
		return nil, err
	}
	switch token := token.(type) {
	case json.Delim:
		switch token {
		case '{':
			object := map[string]any{}
			for decoder.More() {
				keyToken, err := decoder.Token()
				if err != nil {
					return nil, err
				}
				key, ok := keyToken.(string)
				if !ok {
					return nil, fmt.Errorf("object key is not a string")
				}
				if _, exists := object[key]; exists {
					return nil, fmt.Errorf("duplicate object key %q", key)
				}
				value, err := parseJSONValue(decoder)
				if err != nil {
					return nil, err
				}
				object[key] = value
			}
			end, err := decoder.Token()
			if err != nil {
				return nil, err
			}
			if end != json.Delim('}') {
				return nil, fmt.Errorf("object not closed")
			}
			return object, nil
		case '[':
			var array []any
			for decoder.More() {
				value, err := parseJSONValue(decoder)
				if err != nil {
					return nil, err
				}
				array = append(array, value)
			}
			end, err := decoder.Token()
			if err != nil {
				return nil, err
			}
			if end != json.Delim(']') {
				return nil, fmt.Errorf("array not closed")
			}
			if array == nil {
				array = []any{}
			}
			return array, nil
		default:
			return nil, fmt.Errorf("unexpected delimiter %q", token)
		}
	case json.Number:
		return parseSafeInteger(token.String())
	case string:
		return token, nil
	case bool:
		return token, nil
	case nil:
		return nil, nil
	default:
		return nil, fmt.Errorf("unsupported json token %T", token)
	}
}

func parseSafeInteger(raw string) (int64, error) {
	if strings.ContainsAny(raw, ".eE") {
		return 0, fmt.Errorf("floating-point JSON numbers are prohibited")
	}
	if raw == "-0" {
		return 0, fmt.Errorf("negative zero is not canonical")
	}
	value, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("invalid integer %q: %w", raw, err)
	}
	if value < -maxSafeInteger || value > maxSafeInteger {
		return 0, fmt.Errorf("integer %q is outside the RFC 8785 safe range", raw)
	}
	return value, nil
}

func encodeCanonical(value any) ([]byte, error) {
	var buf bytes.Buffer
	if err := appendCanonical(&buf, value); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func appendCanonical(buf *bytes.Buffer, value any) error {
	switch value := value.(type) {
	case nil:
		buf.WriteString("null")
	case bool:
		if value {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case string:
		quoted, err := quoteJSONString(value)
		if err != nil {
			return err
		}
		buf.Write(quoted)
	case int64:
		buf.WriteString(strconv.FormatInt(value, 10))
	case []any:
		buf.WriteByte('[')
		for i, element := range value {
			if i > 0 {
				buf.WriteByte(',')
			}
			if err := appendCanonical(buf, element); err != nil {
				return err
			}
		}
		buf.WriteByte(']')
	case map[string]any:
		keys := make([]string, 0, len(value))
		for key := range value {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		buf.WriteByte('{')
		for i, key := range keys {
			if i > 0 {
				buf.WriteByte(',')
			}
			quoted, err := quoteJSONString(key)
			if err != nil {
				return err
			}
			buf.Write(quoted)
			buf.WriteByte(':')
			if err := appendCanonical(buf, value[key]); err != nil {
				return err
			}
		}
		buf.WriteByte('}')
	default:
		return fmt.Errorf("unsupported canonical value %T", value)
	}
	return nil
}

func quoteJSONString(s string) ([]byte, error) {
	var buf bytes.Buffer
	encoder := json.NewEncoder(&buf)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(s); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(buf.Bytes(), []byte("\n")), nil
}

func rejectUnsupportedGoValues(value reflect.Value) error {
	if !value.IsValid() {
		return nil
	}
	if value.Kind() == reflect.Interface && !value.IsNil() {
		return rejectUnsupportedGoValues(value.Elem())
	}
	if value.Kind() == reflect.Pointer {
		if value.IsNil() {
			return nil
		}
		return rejectUnsupportedGoValues(value.Elem())
	}
	switch value.Kind() {
	case reflect.String:
		if !utf8.ValidString(value.String()) {
			return fmt.Errorf("canonical strings must be valid UTF-8")
		}
	case reflect.Float32, reflect.Float64, reflect.Complex64, reflect.Complex128:
		return fmt.Errorf("floating-point and complex values are prohibited")
	case reflect.Slice:
		if value.Type().Elem().Kind() == reflect.Uint8 {
			return fmt.Errorf("binary byte slices are prohibited in canonical contracts")
		}
		for i := 0; i < value.Len(); i++ {
			if err := rejectUnsupportedGoValues(value.Index(i)); err != nil {
				return err
			}
		}
	case reflect.Array:
		if value.Type().Elem().Kind() == reflect.Uint8 {
			return fmt.Errorf("binary byte arrays are prohibited in canonical contracts")
		}
		for i := 0; i < value.Len(); i++ {
			if err := rejectUnsupportedGoValues(value.Index(i)); err != nil {
				return err
			}
		}
	case reflect.Map:
		for _, key := range value.MapKeys() {
			if key.Kind() != reflect.String {
				return fmt.Errorf("canonical object map keys must be strings")
			}
			if err := rejectUnsupportedGoValues(value.MapIndex(key)); err != nil {
				return err
			}
		}
	case reflect.Struct:
		for i := 0; i < value.NumField(); i++ {
			field := value.Type().Field(i)
			if field.PkgPath != "" {
				continue
			}
			if err := rejectUnsupportedGoValues(value.Field(i)); err != nil {
				return err
			}
		}
	}
	return nil
}
